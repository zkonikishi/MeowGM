using System.Security.Cryptography;
using System.Text.Json;

namespace Mrad.Auction;

// All values come from trusted identity/session mapping, not client UID claims.
public sealed record Owner(string Uid, string AccountId, string Cid, string Realm);
// Exact complete instance snapshot; the host owns its versioned encoding and PVF validation.
// Immutable base64 avoids a mutable byte[] escaping into a transaction plan.
public sealed record ItemInstance(string InstanceId, string ItemId, long Quantity,
    string SnapshotFormat, string SnapshotBase64, long InventoryRevision);
public enum ListingState { Listed, Sold, Cancelled, Expired }
public enum EscrowAction { Hold, DeliverToBuyer, ReturnToSeller }
public enum ApplyResult { Applied, Conflict, InsufficientFunds, EscrowUnavailable, CapacityRejected }
public sealed record Policy(string Version, long MaximumPrice, long MaximumLifetimeSeconds, int FeeBasisPoints);
public sealed record Listing(Guid Id, Owner Seller, ItemInstance Item, long Price,
    long ExpiresAt, long Revision, ListingState State, Policy Policy);
public sealed record Receipt(Guid OperationId, string Fingerprint, Guid ListingId,
    ListingState State, long Revision, string? DeliveryKey, long BuyerDebit, long SellerCredit, long Fee);
public sealed record AssetMove(EscrowAction Action, ItemInstance Item, Owner From, Owner To, string DeliveryKey);
public sealed record MoneyMove(Owner Buyer, Owner Seller, long Debit, long Credit, long Fee);
// Apply must atomically persist all fields, including the receipt. No external notification here.
public sealed record CommitPlan(Listing? Before, Listing After, AssetMove Asset,
    MoneyMove? Money, Receipt Receipt);

public interface IAuctionTransaction
{
    Receipt? FindReceipt(Guid operationId);
    Listing? FindListing(Guid listingId);
    // Authoritative complete snapshot with ownership, tradeability and current-PVF checks.
    ItemInstance? FindTradableOwnedInstance(Owner seller, string instanceId);
    // Must check revision/state/escrow + conditional debit; any rejection has ZERO effects.
    // Applies original inventory revision/lease checks through existing inventory engine.
    // Existing mail engine consumes the stable DeliveryKey; no second mail/asset DB.
    ApplyResult Apply(CommitPlan plan);
}

public interface IAuctionRepository
{
    // Same durable transaction for reads, Apply and receipt, serializable or equivalent CAS.
    // A throw must roll back. Adapter may retry serialization failures with original inputs.
    T InTransaction<T>(Func<IAuctionTransaction, T> action);
}

public sealed class AuctionFault(string code) : Exception(code)
{
    public string Code { get; } = code;
}

public sealed class AuctionService(IAuctionRepository repository, Policy listingPolicy)
{
    public Receipt Place(Owner seller, Guid operationId, Guid listingId, string instanceId,
        long price, long expiresAt, long now)
    {
        ValidateOwner(seller); ValidateOperation(operationId, listingId); Text(instanceId);
        // now is a server clock, deliberately excluded from the replay fingerprint.
        var hash = Fingerprint(new { kind = "place", seller, listingId, instanceId, price, expiresAt });
        return repository.InTransaction(tx =>
        {
            var replay = Replay(tx, operationId, hash); if (replay is not null) return replay;
            ValidatePolicy(listingPolicy);
            if (now < 0 || price <= 0 || price > listingPolicy.MaximumPrice || expiresAt <= now ||
                expiresAt - now > listingPolicy.MaximumLifetimeSeconds) throw new AuctionFault("invalid_listing_terms");
            if (tx.FindListing(listingId) is not null) throw new AuctionFault("listing_exists");
            var item = tx.FindTradableOwnedInstance(seller, instanceId) ?? throw new AuctionFault("item_not_owned_or_tradable");
            ValidateItem(item);
            if (item.InstanceId != instanceId) throw new AuctionFault("snapshot_instance_mismatch");
            var after = new Listing(listingId, seller, item, price, expiresAt, 1, ListingState.Listed, listingPolicy);
            var receipt = new Receipt(operationId, hash, listingId, after.State, 1, null, 0, 0, 0);
            return Commit(tx, new(null, after,
                new(EscrowAction.Hold, item, seller, seller, Key(listingId, "escrow")), null, receipt));
        });
    }

    public Receipt Buy(Owner buyer, Guid operationId, Guid listingId, long expectedRevision, long now)
    {
        ValidateOwner(buyer); ValidateOperation(operationId, listingId);
        var hash = Fingerprint(new { kind = "buy", buyer, listingId, expectedRevision });
        return repository.InTransaction(tx =>
        {
            var replay = Replay(tx, operationId, hash); if (replay is not null) return replay;
            var before = Active(tx, listingId, expectedRevision);
            if (now < 0 || now >= before.ExpiresAt) throw new AuctionFault("listing_expired");
            if (buyer.Realm != before.Seller.Realm) throw new AuctionFault("realm_mismatch");
            // Same UID or internal account cannot trade with its other CID.
            if (buyer.Uid == before.Seller.Uid || buyer.AccountId == before.Seller.AccountId)
                throw new AuctionFault("self_purchase");
            ValidatePolicy(before.Policy);
            // Decimal avoids multiplication overflow for long prices. Policy is listing-bound.
            long fee = checked((long)decimal.Floor((decimal)before.Price * before.Policy.FeeBasisPoints / 10000m));
            long credit = checked(before.Price - fee);
            var after = before with { State = ListingState.Sold, Revision = checked(before.Revision + 1) };
            string key = Key(listingId, "buyer-delivery");
            var receipt = new Receipt(operationId, hash, listingId, after.State, after.Revision, key, before.Price, credit, fee);
            return Commit(tx, new(before, after,
                new(EscrowAction.DeliverToBuyer, before.Item, before.Seller, buyer, key),
                new(buyer, before.Seller, before.Price, credit, fee), receipt));
        });
    }

    public Receipt Cancel(Owner seller, Guid operationId, Guid listingId, long expectedRevision, long now)
    {
        ValidateOwner(seller); ValidateOperation(operationId, listingId);
        var hash = Fingerprint(new { kind = "cancel", seller, listingId, expectedRevision });
        return repository.InTransaction(tx =>
        {
            var replay = Replay(tx, operationId, hash); if (replay is not null) return replay;
            var before = Active(tx, listingId, expectedRevision);
            if (seller != before.Seller) throw new AuctionFault("not_listing_owner");
            if (now < 0 || now >= before.ExpiresAt) throw new AuctionFault("listing_expired");
            return Return(tx, before, operationId, hash, ListingState.Cancelled);
        });
    }

    // Internal scheduler only; do not expose this as an unauthenticated player operation.
    public Receipt Expire(Guid operationId, Guid listingId, long expectedRevision, long now)
    {
        ValidateOperation(operationId, listingId);
        var hash = Fingerprint(new { kind = "expire", listingId, expectedRevision });
        return repository.InTransaction(tx =>
        {
            var replay = Replay(tx, operationId, hash); if (replay is not null) return replay;
            var before = Active(tx, listingId, expectedRevision);
            if (now < before.ExpiresAt) throw new AuctionFault("not_expired");
            return Return(tx, before, operationId, hash, ListingState.Expired);
        });
    }

    private static Receipt Return(IAuctionTransaction tx, Listing before, Guid operationId, string hash, ListingState state)
    {
        var after = before with { State = state, Revision = checked(before.Revision + 1) };
        // Cancellation and expiry share one seller return key; competing terminals cannot duplicate.
        string key = Key(before.Id, "seller-return");
        var receipt = new Receipt(operationId, hash, before.Id, state, after.Revision, key, 0, 0, 0);
        return Commit(tx, new(before, after,
            new(EscrowAction.ReturnToSeller, before.Item, before.Seller, before.Seller, key), null, receipt));
    }

    private static Receipt Commit(IAuctionTransaction tx, CommitPlan plan)
    {
        var result = tx.Apply(plan);
        // NEVER ignore debit failure or return a sold receipt after a rejected plan.
        if (result != ApplyResult.Applied) throw new AuctionFault(result switch
        {
            ApplyResult.InsufficientFunds => "insufficient_funds",
            ApplyResult.EscrowUnavailable => "escrow_unavailable",
            ApplyResult.CapacityRejected => "capacity_rejected",
            _ => "transaction_conflict"
        });
        return plan.Receipt;
    }

    private static Listing Active(IAuctionTransaction tx, Guid id, long expectedRevision)
    {
        var listing = tx.FindListing(id) ?? throw new AuctionFault("listing_not_found");
        if (listing.State != ListingState.Listed) throw new AuctionFault("listing_not_active");
        if (expectedRevision <= 0 || listing.Revision != expectedRevision) throw new AuctionFault("revision_conflict");
        return listing;
    }
    private static Receipt? Replay(IAuctionTransaction tx, Guid operation, string fingerprint)
    {
        var receipt = tx.FindReceipt(operation);
        if (receipt is not null && receipt.Fingerprint != fingerprint) throw new AuctionFault("operation_conflict");
        return receipt;
    }
    private static string Fingerprint<T>(T value) => Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value)));
    private static string Key(Guid listing, string purpose) => $"auction:v1:{listing:N}:{purpose}";
    private static void ValidateOperation(Guid operation, Guid listing)
    { if (operation == Guid.Empty || listing == Guid.Empty) throw new AuctionFault("invalid_operation"); }
    private static void Text(string value)
    { if (string.IsNullOrWhiteSpace(value) || value.Length > 256 || value.Any(char.IsControl)) throw new AuctionFault("invalid_identifier"); }
    private static void ValidateOwner(Owner owner)
    { Text(owner.Uid); Text(owner.AccountId); Text(owner.Cid); Text(owner.Realm); }
    private static void ValidatePolicy(Policy policy)
    {
        Text(policy.Version);
        if (policy.MaximumPrice <= 0 || policy.MaximumLifetimeSeconds <= 0 || policy.FeeBasisPoints is < 0 or > 10000)
            throw new AuctionFault("invalid_policy");
    }
    private static void ValidateItem(ItemInstance item)
    {
        Text(item.InstanceId); Text(item.ItemId); Text(item.SnapshotFormat);
        if (item.Quantity <= 0 || item.InventoryRevision < 0 || item.SnapshotBase64.Length > 2_000_000)
            throw new AuctionFault("invalid_item_snapshot");
        try { if (Convert.FromBase64String(item.SnapshotBase64).Length == 0) throw new FormatException(); }
        catch (FormatException) { throw new AuctionFault("invalid_item_snapshot"); }
    }
}

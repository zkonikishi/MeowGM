using Mrad.Auction;
using System.Text.Json;

var checks = new List<string>();
void Check(string name, Action test) { test(); checks.Add(name); Console.WriteLine("PASS " + name); }
void Equal<T>(T expected, T actual) { if (!EqualityComparer<T>.Default.Equals(expected, actual)) throw new Exception($"Expected {expected}; got {actual}"); }
void Fault(string code, Action test) { try { test(); } catch (AuctionFault e) when (e.Code == code) { return; } throw new Exception("Expected fault " + code); }
var seller = new Owner("user-seller", "100", "1", "cn");
var buyer = new Owner("user-buyer", "200", "2", "cn");
var second = new Owner("user-second", "300", "3", "cn");
var policy = new Policy("test-policy-not-production", long.MaxValue, 1000, 321);
var item = new ItemInstance("instance-1", "item-7", 3, "synthetic-full-instance-v1", Convert.ToBase64String(new byte[] { 1, 4, 8, 16, 32, 64 }), 7);
(MemoryRepository repo, AuctionService service, Guid id) Fixture(long funds = 2000)
{
    var repo = new MemoryRepository(); repo.Items[(seller, item.InstanceId)] = item;
    repo.Wallets[buyer.AccountId] = funds; repo.Wallets[second.AccountId] = 2000; repo.Wallets[seller.AccountId] = 0;
    return (repo, new AuctionService(repo, policy), Guid.NewGuid());
}
void Place((MemoryRepository repo, AuctionService service, Guid id) f, long price = 1000) => f.service.Place(seller, Guid.NewGuid(), f.id, item.InstanceId, price, 200, 100);

Check("place removes complete instance into escrow", () => {
    var f = Fixture(); Place(f);
    Equal(false, f.repo.Items.ContainsKey((seller, item.InstanceId)));
    Equal(item, f.repo.Escrow[f.id]); Equal(ListingState.Listed, f.repo.Listings[f.id].State);
});
Check("successful buy conserves money and full instance snapshot", () => {
    var f = Fixture(); Place(f); var r = f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101);
    Equal(1000L, r.BuyerDebit); Equal(r.BuyerDebit, r.SellerCredit + r.Fee);
    Equal(2000L, f.repo.Wallets[buyer.AccountId] + f.repo.Wallets[seller.AccountId] + f.repo.Fees);
    Equal(item, f.repo.Deliveries[r.DeliveryKey!].Item); Equal(buyer, f.repo.Deliveries[r.DeliveryKey!].To);
    Equal(0, f.repo.Escrow.Count); Equal(ListingState.Sold, f.repo.Listings[f.id].State);
});
Check("insufficient funds cannot produce sold receipt (reference regression)", () => {
    var f = Fixture(999); Place(f);
    Fault("insufficient_funds", () => f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101));
    Equal(ListingState.Listed, f.repo.Listings[f.id].State); Equal(999L, f.repo.Wallets[buyer.AccountId]);
    Equal(1, f.repo.Escrow.Count); Equal(0, f.repo.Deliveries.Count); Equal(1, f.repo.Receipts.Count);
});
Check("debit engine rejection even with observed balance aborts", () => {
    var f = Fixture(); Place(f); f.repo.Reject = ApplyResult.InsufficientFunds;
    Fault("insufficient_funds", () => f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101));
    Equal(2000L, f.repo.Wallets[buyer.AccountId]); Equal(ListingState.Listed, f.repo.Listings[f.id].State);
});
Check("delivery capacity rejection preserves money and escrow", () => {
    var f = Fixture(); Place(f); f.repo.Reject = ApplyResult.CapacityRejected;
    Fault("capacity_rejected", () => f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101));
    Equal(2000L, f.repo.Wallets[buyer.AccountId]); Equal(1, f.repo.Escrow.Count); Equal(0, f.repo.Deliveries.Count);
});
Check("transaction throw after staged mutations rolls everything back", () => {
    var f = Fixture(); Place(f); f.repo.ThrowAfterApply = true;
    try { f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101); throw new Exception("Expected injected failure"); }
    catch (IOException) { }
    Equal(2000L, f.repo.Wallets[buyer.AccountId]); Equal(0L, f.repo.Wallets[seller.AccountId]);
    Equal(ListingState.Listed, f.repo.Listings[f.id].State); Equal(0, f.repo.Deliveries.Count); Equal(1, f.repo.Receipts.Count);
});
Check("same operation replay after time advances returns original receipt", () => {
    var f = Fixture(); Place(f); var op = Guid.NewGuid();
    var first = f.service.Buy(buyer, op, f.id, 1, 101); var replay = f.service.Buy(buyer, op, f.id, 1, 999);
    Equal(first, replay); Equal(1, f.repo.Deliveries.Count); Equal(1000L, f.repo.Wallets[buyer.AccountId]);
});
Check("new service instance replays retained fixture receipt (not disk restart)", () => {
    var f = Fixture(); Place(f); var op = Guid.NewGuid(); var first = f.service.Buy(buyer, op, f.id, 1, 101);
    var reopened = new AuctionService(f.repo, policy with { FeeBasisPoints = 9999 });
    Equal(first, reopened.Buy(buyer, op, f.id, 1, 300)); Equal(1, f.repo.Deliveries.Count);
});
Check("same operation different actor conflicts", () => {
    var f = Fixture(); Place(f); var op = Guid.NewGuid(); f.service.Buy(buyer, op, f.id, 1, 101);
    Fault("operation_conflict", () => f.service.Buy(second, op, f.id, 1, 101));
    Equal(2000L, f.repo.Wallets[second.AccountId]);
});
Check("same placement operation changed terms conflicts", () => {
    var f = Fixture(); var op = Guid.NewGuid(); f.service.Place(seller, op, f.id, item.InstanceId, 1000, 200, 100);
    Fault("operation_conflict", () => f.service.Place(seller, op, f.id, item.InstanceId, 1001, 200, 100));
});
Check("cancel returns complete escrow once", () => {
    var f = Fixture(); Place(f); var op = Guid.NewGuid(); var r = f.service.Cancel(seller, op, f.id, 1, 101);
    Equal(ListingState.Cancelled, r.State); Equal(item, f.repo.Deliveries[r.DeliveryKey!].Item);
    Equal(r, f.service.Cancel(seller, op, f.id, 1, 999)); Equal(1, f.repo.Deliveries.Count);
});
Check("expiry boundary and seller return key are deterministic", () => {
    var f = Fixture(); Place(f);
    Fault("not_expired", () => f.service.Expire(Guid.NewGuid(), f.id, 1, 199));
    Fault("listing_expired", () => f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 200));
    var r = f.service.Expire(Guid.NewGuid(), f.id, 1, 200);
    Equal(ListingState.Expired, r.State); Equal($"auction:v1:{f.id:N}:seller-return", r.DeliveryKey);
});
Check("foreign UID CID and realm cannot cancel", () => {
    foreach (var other in new[] { buyer, seller with { Cid = "other" }, seller with { Realm = "other" } }) {
        var f = Fixture(); Place(f); Fault("not_listing_owner", () => f.service.Cancel(other, Guid.NewGuid(), f.id, 1, 101));
    }
});
Check("cross realm and same UID different CID buy rejected", () => {
    var f = Fixture(); Place(f);
    Fault("realm_mismatch", () => f.service.Buy(buyer with { Realm = "other" }, Guid.NewGuid(), f.id, 1, 101));
    Fault("self_purchase", () => f.service.Buy(seller with { Cid = "another" }, Guid.NewGuid(), f.id, 1, 101));
});
Check("stale listing revision rejected", () => {
    var f = Fixture(); Place(f); Fault("revision_conflict", () => f.service.Buy(buyer, Guid.NewGuid(), f.id, 2, 101));
});
Check("invalid price lifetime and absent tradable item rejected", () => {
    var f = Fixture();
    Fault("invalid_listing_terms", () => f.service.Place(seller, Guid.NewGuid(), f.id, item.InstanceId, 0, 200, 100));
    Fault("invalid_listing_terms", () => f.service.Place(seller, Guid.NewGuid(), f.id, item.InstanceId, 1, 1101, 100));
    Fault("item_not_owned_or_tradable", () => f.service.Place(buyer, Guid.NewGuid(), f.id, item.InstanceId, 1, 200, 100));
});
Check("maximum price fee math does not overflow", () => {
    var f = Fixture(long.MaxValue); Place(f, long.MaxValue);
    var r = f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101);
    Equal(long.MaxValue, checked(r.SellerCredit + r.Fee));
});
Check("listing fee policy remains bound across service policy changes", () => {
    var f = Fixture(); Place(f); var newer = new AuctionService(f.repo, policy with { FeeBasisPoints = 9999 });
    var r = newer.Buy(buyer, Guid.NewGuid(), f.id, 1, 101); Equal(32L, r.Fee);
});
Check("two buyers compete for one listing in serialized in-memory fixture", () => {
    var f = Fixture(); Place(f); int success = 0, failed = 0;
    Parallel.ForEach(new[] { buyer, second }, owner => {
        try { f.service.Buy(owner, Guid.NewGuid(), f.id, 1, 101); Interlocked.Increment(ref success); }
        catch (AuctionFault) { Interlocked.Increment(ref failed); }
    });
    Equal(1, success); Equal(1, failed); Equal(1, f.repo.Deliveries.Count);
    Equal(4000L, f.repo.Wallets[buyer.AccountId] + f.repo.Wallets[second.AccountId] + f.repo.Wallets[seller.AccountId] + f.repo.Fees);
});
Check("cancel and buy competition produces one terminal and one delivery", () => {
    var f = Fixture(); Place(f); int success = 0;
    Parallel.Invoke(
        () => { try { f.service.Cancel(seller, Guid.NewGuid(), f.id, 1, 101); Interlocked.Increment(ref success); } catch (AuctionFault) {} },
        () => { try { f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101); Interlocked.Increment(ref success); } catch (AuctionFault) {} });
    Equal(1, success); Equal(1, f.repo.Deliveries.Count); Equal(0, f.repo.Escrow.Count);
});
Check("same instance cannot be listed twice under another listing ID", () => {
    var f = Fixture(); Place(f);
    Fault("item_not_owned_or_tradable", () => f.service.Place(seller, Guid.NewGuid(), Guid.NewGuid(), item.InstanceId, 1000, 200, 100));
    Equal(1, f.repo.Listings.Count); Equal(1, f.repo.Escrow.Count);
});
Check("missing escrow rejects purchase without debit or sold state", () => {
    var f = Fixture(); Place(f); f.repo.Escrow.Clear();
    Fault("escrow_unavailable", () => f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101));
    Equal(2000L, f.repo.Wallets[buyer.AccountId]); Equal(0L, f.repo.Wallets[seller.AccountId]);
    Equal(ListingState.Listed, f.repo.Listings[f.id].State); Equal(0, f.repo.Deliveries.Count);
});
Check("changed complete instance snapshot rejects purchase", () => {
    var f = Fixture(); Place(f); f.repo.Escrow[f.id] = item with { SnapshotBase64 = "AA==" };
    Fault("escrow_unavailable", () => f.service.Buy(buyer, Guid.NewGuid(), f.id, 1, 101));
    Equal(2000L, f.repo.Wallets[buyer.AccountId]); Equal(ListingState.Listed, f.repo.Listings[f.id].State);
});
Check("after cancel a different expiry operation cannot return twice", () => {
    var f = Fixture(); Place(f); f.service.Cancel(seller, Guid.NewGuid(), f.id, 1, 199);
    Fault("listing_not_active", () => f.service.Expire(Guid.NewGuid(), f.id, 1, 200));
    Equal(1, f.repo.Deliveries.Count);
});
Check("changed expected revision under the same operation conflicts", () => {
    var f = Fixture(); Place(f); var op = Guid.NewGuid(); f.service.Buy(buyer, op, f.id, 1, 101);
    Fault("operation_conflict", () => f.service.Buy(buyer, op, f.id, 2, 101));
});
Check("buyer delivery retains exact trusted CID without any online connection", () => {
    var f = Fixture(); Place(f); var recipient = buyer with { Cid = "buyer-second-character" };
    var r = f.service.Buy(recipient, Guid.NewGuid(), f.id, 1, 101);
    Equal(recipient, f.repo.Deliveries[r.DeliveryKey!].To);
    Equal(seller, f.repo.Deliveries[r.DeliveryKey!].From);
    // The plan has no online connection requirement; actual offline mail delivery is host work.
    Equal(item, f.repo.Deliveries[r.DeliveryKey!].Item);
});
Check("same buyer UID competing CIDs result in one exact recipient", () => {
    var f = Fixture(); Place(f); var other = buyer with { Cid = "buyer-other-cid" }; int success = 0;
    Parallel.ForEach(new[] { buyer, other }, recipient => {
        try { f.service.Buy(recipient, Guid.NewGuid(), f.id, 1, 101); Interlocked.Increment(ref success); }
        catch (AuctionFault) { }
    });
    Equal(1, success); Equal(1, f.repo.Deliveries.Count);
    Equal(true, new[] { buyer, other }.Contains(f.repo.Deliveries.Values.Single().To));
    Equal(1000L, f.repo.Wallets[buyer.AccountId]);
});
Check("concurrent retries of one operation return one receipt and debit", () => {
    var f = Fixture(); Place(f); var op = Guid.NewGuid(); var receipts = new System.Collections.Concurrent.ConcurrentBag<Receipt>();
    Parallel.For(0, 8, _ => receipts.Add(f.service.Buy(buyer, op, f.id, 1, 101)));
    Equal(8, receipts.Count); Equal(1, receipts.Distinct().Count());
    Equal(1, f.repo.Deliveries.Count); Equal(1000L, f.repo.Wallets[buyer.AccountId]);
});
Check("retry cannot redirect the committed delivery to a different CID", () => {
    var f = Fixture(); Place(f); var op = Guid.NewGuid(); var r = f.service.Buy(buyer, op, f.id, 1, 101);
    Fault("operation_conflict", () => f.service.Buy(buyer with { Cid = "different" }, op, f.id, 1, 102));
    Equal(buyer, f.repo.Deliveries[r.DeliveryKey!].To); Equal(1, f.repo.Deliveries.Count);
});
CnSearchChecks.Run(Check, args);
Console.WriteLine(JsonSerializer.Serialize(new { passed = checks.Count, failed = 0,
    implementation = "independent-domain-and-transaction-contract", backend = "serialized-in-memory-fixture-only",
    databaseConcurrencyVerified = false, deployed = false, clientVerified = false }));

// TEST DOUBLE ONLY. Not a production wallet, inventory, mail or persistence engine.
sealed class MemoryRepository : IAuctionRepository
{
    private readonly object gate = new();
    public Dictionary<Guid, Listing> Listings = [];
    public Dictionary<Guid, Receipt> Receipts = [];
    public Dictionary<(Owner, string), ItemInstance> Items = [];
    public Dictionary<Guid, ItemInstance> Escrow = [];
    public Dictionary<string, AssetMove> Deliveries = [];
    public Dictionary<string, long> Wallets = [];
    public long Fees;
    public ApplyResult? Reject;
    public bool ThrowAfterApply;
    public T InTransaction<T>(Func<IAuctionTransaction, T> action)
    {
        lock (gate) {
            var staged = new MemoryRepository { Listings = new(Listings), Receipts = new(Receipts),
                Items = new(Items), Escrow = new(Escrow), Deliveries = new(Deliveries),
                Wallets = new(Wallets), Fees = Fees, Reject = Reject, ThrowAfterApply = ThrowAfterApply };
            var result = action(new Transaction(staged));
            Listings = staged.Listings; Receipts = staged.Receipts; Items = staged.Items;
            Escrow = staged.Escrow; Deliveries = staged.Deliveries; Wallets = staged.Wallets; Fees = staged.Fees;
            return result;
        }
    }
    private sealed class Transaction(MemoryRepository state) : IAuctionTransaction
    {
        public Receipt? FindReceipt(Guid operationId) => state.Receipts.GetValueOrDefault(operationId);
        public Listing? FindListing(Guid listingId) => state.Listings.GetValueOrDefault(listingId);
        public ItemInstance? FindTradableOwnedInstance(Owner seller, string instanceId) => state.Items.GetValueOrDefault((seller, instanceId));
        public ApplyResult Apply(CommitPlan plan)
        {
            if (state.Reject.HasValue) return state.Reject.Value;
            if (state.Receipts.ContainsKey(plan.Receipt.OperationId) || FindListing(plan.After.Id) != plan.Before) return ApplyResult.Conflict;
            if (plan.Money is {} money) {
                if (state.Wallets.GetValueOrDefault(money.Buyer.AccountId) < money.Debit) return ApplyResult.InsufficientFunds;
                // Only fixture accounting; production adapter must reuse Max wallet operations.
                state.Wallets[money.Buyer.AccountId] -= money.Debit;
                state.Wallets[money.Seller.AccountId] = checked(state.Wallets.GetValueOrDefault(money.Seller.AccountId) + money.Credit);
                state.Fees = checked(state.Fees + money.Fee);
            }
            if (plan.Asset.Action == EscrowAction.Hold) {
                if (FindTradableOwnedInstance(plan.Asset.From, plan.Asset.Item.InstanceId) != plan.Asset.Item) return ApplyResult.Conflict;
                state.Items.Remove((plan.Asset.From, plan.Asset.Item.InstanceId)); state.Escrow.Add(plan.After.Id, plan.Asset.Item);
            } else {
                if (state.Escrow.GetValueOrDefault(plan.After.Id) != plan.Asset.Item) return ApplyResult.EscrowUnavailable;
                state.Escrow.Remove(plan.After.Id); state.Deliveries.Add(plan.Asset.DeliveryKey, plan.Asset);
            }
            state.Listings[plan.After.Id] = plan.After; state.Receipts.Add(plan.Receipt.OperationId, plan.Receipt);
            if (state.ThrowAfterApply) throw new IOException("Injected after staged mutations");
            return ApplyResult.Applied;
        }
    }
}

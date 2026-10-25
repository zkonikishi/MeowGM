namespace Mrad.Delta109;

// Values are reference 1.0.9 release behavior, not independently verified official policy.
public sealed record RenamePolicy(long CooldownSeconds, long OldNameReservationSeconds)
{
    public static RenamePolicy Reference109 { get; } = new(90L * 86400, 180L * 86400);
}
// Keys must use the host's actual name validation/collation; no guessed normalization here.
public sealed record RenameState(string AccountId, string Cid, string Realm,
    string CurrentNameKey, long Revision, long? LastRenamedAt);
public sealed record NameAvailability(bool CurrentCharacterExists, long? ReservedUntil);
public sealed record RenamePlan(RenameState Before, string NewNameKey, long RenamedAt,
    long NextRenameAndPurchaseAt, string ReservedOldNameKey, long OldNameReservedUntil);

public sealed class RenameRuleFault(string code) : Exception(code)
{
    public string Code { get; } = code;
}

public static class RenameRules
{
    public static long? NextAllowedAt(long? lastRenamedAt, RenamePolicy policy)
    {
        Validate(policy);
        if (lastRenamedAt is null) return null;
        if (lastRenamedAt < 0) throw new RenameRuleFault("invalid_rename_timestamp");
        try { return checked(lastRenamedAt.Value + policy.CooldownSeconds); }
        catch (OverflowException) { throw new RenameRuleFault("rename_timestamp_overflow"); }
    }

    public static bool CanPurchaseOrRename(long? lastRenamedAt, long now, RenamePolicy policy)
    {
        if (now < 0 || lastRenamedAt > now) throw new RenameRuleFault("invalid_rename_clock");
        long? until = NextAllowedAt(lastRenamedAt, policy);
        return until is null || now >= until;
    }

    public static bool NameAvailable(NameAvailability availability, long now)
    {
        if (now < 0 || availability.ReservedUntil < 0) throw new RenameRuleFault("invalid_name_reservation");
        // Applies to every CID including the old owner; no same-user bypass.
        return !availability.CurrentCharacterExists && (availability.ReservedUntil is null || now >= availability.ReservedUntil);
    }

    public static RenamePlan Plan(RenameState state, string trustedAccountId, string trustedCid,
        string trustedRealm, long expectedRevision, string targetNameKey, NameAvailability availability,
        bool validUnexpiredCard, long now, RenamePolicy policy)
    {
        if (state.AccountId != trustedAccountId || state.Cid != trustedCid || state.Realm != trustedRealm)
            throw new RenameRuleFault("rename_owner_mismatch");
        if (expectedRevision < 0 || state.Revision != expectedRevision) throw new RenameRuleFault("rename_revision_conflict");
        if (string.IsNullOrWhiteSpace(targetNameKey) || targetNameKey == state.CurrentNameKey)
            throw new RenameRuleFault("invalid_rename_target");
        if (!CanPurchaseOrRename(state.LastRenamedAt, now, policy)) throw new RenameRuleFault("rename_cooldown");
        if (!NameAvailable(availability, now)) throw new RenameRuleFault("rename_name_unavailable");
        if (!validUnexpiredCard) throw new RenameRuleFault("rename_card_unavailable");
        try {
            return new(state, targetNameKey, now, checked(now + policy.CooldownSeconds),
                state.CurrentNameKey, checked(now + policy.OldNameReservationSeconds));
        } catch (OverflowException) { throw new RenameRuleFault("rename_timestamp_overflow"); }
    }

    private static void Validate(RenamePolicy policy)
    {
        if (policy.CooldownSeconds <= 0 || policy.OldNameReservationSeconds <= 0)
            throw new RenameRuleFault("invalid_rename_policy");
    }
}

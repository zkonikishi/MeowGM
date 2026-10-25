using System.Buffers.Binary;
using System.Text.Json;
using DNF115CN.Protocol.Game;
using Mrad.Delta109;

var checks = new List<string>();
void Check(string name, Action action) { action(); checks.Add(name); Console.WriteLine("PASS " + name); }
void Require(bool value) { if (!value) throw new Exception("Assertion failed"); }
void Fault(string code, Action action) {
    try { action(); } catch (RenameRuleFault e) when (e.Code == code) { return; }
    throw new Exception("Expected " + code);
}
var policy = RenamePolicy.Reference109;
const long now = 2_000_000_000;
var original = new RenameState("account", "cid", "cn", "old-name", 8, null);
RenamePlan Plan(RenameState? state = null, string account = "account", string cid = "cid", string realm = "cn",
    long revision = 8, NameAvailability? availability = null, bool card = true, long clock = now) =>
    RenameRules.Plan(state ?? original, account, cid, realm, revision, "new-name", availability ?? new(false, null), card, clock, policy);

Check("first rename and card purchase allowed without history", () => Require(RenameRules.CanPurchaseOrRename(null, now, policy)));
Check("rename and purchase blocked one second before 90 days", () => {
    long renamed = now - policy.CooldownSeconds + 1;
    Require(!RenameRules.CanPurchaseOrRename(renamed, now, policy));
    Fault("rename_cooldown", () => Plan(original with { LastRenamedAt = renamed }));
});
Check("90 day boundary permits next rename and purchase", () => Require(RenameRules.CanPurchaseOrRename(now - policy.CooldownSeconds, now, policy)));
Check("old name blocked until exact 180 day boundary for every CID", () => {
    Require(!RenameRules.NameAvailable(new(false, now + 1), now));
    Require(RenameRules.NameAvailable(new(false, now), now));
    Require(!RenameRules.NameAvailable(new(true, now - 1), now));
});
Check("plan carries original name reservation and both deadlines", () => {
    var result = Plan(); Require(result.ReservedOldNameKey == original.CurrentNameKey);
    Require(result.OldNameReservedUntil == now + 180L * 86400);
    Require(result.NextRenameAndPurchaseAt == now + 90L * 86400);
    Require(original.LastRenamedAt is null && original.CurrentNameKey == "old-name");
});
Check("cross account CID and realm rejected", () => {
    Fault("rename_owner_mismatch", () => Plan(account: "other"));
    Fault("rename_owner_mismatch", () => Plan(cid: "other"));
    Fault("rename_owner_mismatch", () => Plan(realm: "other"));
});
Check("stale revision name collision and missing card rejected without a plan", () => {
    Fault("rename_revision_conflict", () => Plan(revision: 7));
    Fault("rename_name_unavailable", () => Plan(availability: new(true, null)));
    Fault("rename_name_unavailable", () => Plan(availability: new(false, now + 1)));
    Fault("rename_card_unavailable", () => Plan(card: false));
});
Check("future timestamps and deadline overflow fail closed", () => {
    Fault("invalid_rename_clock", () => RenameRules.CanPurchaseOrRename(now + 1, now, policy));
    Fault("rename_timestamp_overflow", () => RenameRules.NextAllowedAt(long.MaxValue, policy));
    Fault("rename_timestamp_overflow", () => Plan(clock: long.MaxValue));
});
Check("reuse actual Max duplicate-check parser, no guessed rename packet", () => {
    var request = new byte[16]; BinaryPrimitives.WriteUInt32LittleEndian(request, 4);
    "Name"u8.CopyTo(request.AsSpan(4)); Require(CharacterNameCn115.ParseCheck(request).SequenceEqual("Name"u8.ToArray()));
    request[8] = 1;
    try { CharacterNameCn115.ParseCheck(request); throw new Exception("Expected bad tail"); } catch (InvalidDataException) { }
});

// Next item: test current implementation before deciding it needs a patch.
Check("actual Max option replay preserves explicit zero and nonzero", () => {
    var body = new byte[5121]; BinaryPrimitives.WriteUInt16LittleEndian(body.AsSpan(1), 1); body[3] = 5;
    CharacterOptionsCn115.Group[] groups = [new(18, [new(0, 0)]), new(19, [new(4, 0)]), new(20, [new(7, 1)])];
    var result = CharacterOptionsCn115.AppendToDungeonSettings(body, groups);
    int offset = 532;
    foreach (var group in groups) {
        int capacity = CharacterOptionsCn115.Capacity(group.Id);
        var entry = group.Entries.Single();
        Require(BinaryPrimitives.ReadUInt16LittleEndian(result.AsSpan(offset + 4 + entry.Key * 2)) == entry.Value);
        Require(result[offset + 4 + capacity * 2 + entry.Key] == 1);
        offset += 4 + capacity * 3;
    }
    Require(body[1] == 1); // serializer cloned source rather than mutating it
});
Check("actual Max parser retains a persisted-off zero option", () => {
    var payload = new byte[16]; payload[2] = 19;
    BinaryPrimitives.WriteUInt32LittleEndian(payload.AsSpan(4), 1);
    BinaryPrimitives.WriteUInt16LittleEndian(payload.AsSpan(8), 4);
    var parsed = CharacterOptionsCn115.Parse(payload);
    Require(parsed.Entries.Single().Value == 0);
});
Console.WriteLine(JsonSerializer.Serialize(new { passed = checks.Count, failed = 0,
    rename = "pure-rule-candidate-not-integrated", options = "actual-linked-Max-protocol-source",
    databaseVerified = false, deployed = false, clientVerified = false }));

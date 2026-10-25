using Mrad.Auction;
using System.Text.Json;

static class CnSearchChecks
{
    public static void Run(Action<string, Action> check, string[] args)
    {
        var source = new CnCatalogSource("zh-CN", "cn", "synthetic-cn-pvf-v1", true);
        CnCatalogItem[] rows = [new("38", "鬼剑士福包", "stackable", ["Ghost Knight Gift"]),
            new("100", "测试：勇者之剑", "equipment"), new("101", "测试：勇者短剑", "equipment"),
            new("200", "测试药剂Ａ", "stackable"), new("300", null, "equipment"),
            new("301", "equipment/us/sword.equ", "equipment")];
        var catalog = new CnItemCatalog(source, rows);
        void Require(bool value) { if (!value) throw new Exception("CN catalog assertion failed"); }
        void Fault(string code, Action action) {
            try { action(); } catch (AuctionFault e) when (e.Code == code) { return; }
            throw new Exception("Expected " + code);
        }
        check("CN search uses Chinese item names", () => {
            var result = catalog.Search("勇者");
            Require(result.Items.Count == 2 && result.Items.All(x => x.Name.Contains("勇者")));
            Require(result.Items.All(x => x.Category == "装备"));
        });
        check("explicit English alias matches but still displays CN name", () => {
            var result = catalog.Search("ghost knight");
            Require(result.Items.Count == 1 && result.Items[0].Name == "鬼剑士福包");
        });
        check("fullwidth text whitespace and case normalize for matching", () => {
            Require(catalog.Search("  ｇｈｏｓｔ　ＫＮＩＧＨＴ ").Items.Count == 1);
            Require(catalog.Search("测试药剂a").Items.Single().ItemId == "200");
        });
        check("exact fullwidth item ID resolves CN name", () => {
            Require(catalog.Search("３８").Items.Single().Name == "鬼剑士福包");
        });
        check("missing names and raw resource paths never fall back to US captions", () => {
            foreach (string id in new[] { "300", "301", "999" }) {
                var result = catalog.Resolve(id);
                Require(!result.NameAvailable && result.Name.StartsWith("未收录物品"));
                Require(!result.Name.Contains("sword"));
            }
            Require(catalog.Search("us/sword").Items.Count == 0);
        });
        check("US or incomplete resource catalog rejected", () => {
            Fault("cn_catalog_unavailable", () => new CnItemCatalog(source with { Locale = "en-US" }, rows));
            Fault("cn_catalog_unavailable", () => new CnItemCatalog(source with { Realm = "us" }, rows));
            Fault("cn_catalog_unavailable", () => new CnItemCatalog(source with { Complete = false }, rows));
        });
        check("CN pagination stable and bound to resource query and page size", () => {
            var first = catalog.Search("勇者", 1); Require(first.NextCursor is not null);
            var second = catalog.Search("勇者", 1, first.NextCursor);
            Require(first.Items.Single().ItemId != second.Items.Single().ItemId && second.NextCursor is null);
            Fault("cn_search_cursor_conflict", () => catalog.Search("福包", 1, first.NextCursor));
            Fault("cn_search_cursor_conflict", () => catalog.Search("勇者", 2, first.NextCursor));
            Fault("cn_search_cursor_conflict", () => new CnItemCatalog(source with { ResourceFingerprint = "new-pvf" }, rows).Search("勇者", 1, first.NextCursor));
            Fault("cn_search_cursor_conflict", () => new CnItemCatalog(source, rows.Append(new("400", "另一把勇者剑", "equipment"))).Search("勇者", 1, first.NextCursor));
        });
        check("unknown kinds duplicate IDs and invalid input rejected", () => {
            Fault("invalid_cn_item_kind", () => new CnItemCatalog(source, [new("1", "x", "unknown")]));
            Fault("duplicate_cn_item_id", () => new CnItemCatalog(source, [rows[0], rows[0]]));
            Fault("invalid_cn_search", () => catalog.Search(new string('剑', 81)));
            Fault("invalid_cn_search", () => catalog.Search("剑", 101));
            Fault("invalid_cn_item_id", () => catalog.Resolve("../38"));
        });
        int argument = Array.IndexOf(args, "--cn-catalog");
        if (argument >= 0) {
            if (argument + 1 >= args.Length) throw new ArgumentException("Missing CN catalog sample");
            var fixture = JsonSerializer.Deserialize<CatalogFile>(File.ReadAllText(args[argument + 1]),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true }) ?? throw new Exception("Missing catalog");
            check("real CN resource sample: Chinese search and exact ID display", () => {
                var actual = new CnItemCatalog(fixture.Source, fixture.Items);
                var page = actual.Search("剑", 100);
                Require(page.Items.Count > 0 && page.Items.All(x => x.Name.Contains('剑')));
                foreach (var row in page.Items) Require(actual.Resolve(row.ItemId).Name == row.Name);
                Require(page.Locale == "zh-CN");
            });
        }
    }
    private sealed record CatalogFile(CnCatalogSource Source, CnCatalogItem[] Items);
}

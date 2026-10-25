using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Mrad.Auction;

public sealed record CnCatalogSource(string Locale, string Realm, string ResourceFingerprint, bool Complete);
public sealed record CnCatalogItem(string ItemId, string? Name, string Kind, string[]? SearchAliases = null);
public sealed record CnSearchItem(string ItemId, string Name, string Kind, string Category, bool NameAvailable);
public sealed record CnSearchCursor(string Context, uint AfterItemId);
public sealed record CnSearchPage(string Locale, string ResourceFingerprint,
    IReadOnlyList<CnSearchItem> Items, CnSearchCursor? NextCursor);

/// <summary>
/// CN item identity/name lookup for auction listings and search. The host supplies
/// the current CN PVF catalog, never the US reference catalog or listing captions.
/// This is a name index, not an auction repository, tradeability check or translator.
/// </summary>
public sealed class CnItemCatalog
{
    private sealed record Indexed(uint Id, CnSearchItem Item, string Text);
    private readonly CnCatalogSource source;
    private readonly SortedDictionary<uint, Indexed> items = [];
    private readonly string revision;

    public CnItemCatalog(CnCatalogSource source, IEnumerable<CnCatalogItem> rows)
    {
        if (source.Locale != "zh-CN" || source.Realm != "cn" || !source.Complete ||
            string.IsNullOrWhiteSpace(source.ResourceFingerprint) || source.ResourceFingerprint.Length > 256)
            throw new AuctionFault("cn_catalog_unavailable");
        this.source = source;
        foreach (var row in rows)
        {
            uint id = Id(row.ItemId);
            if (row.Kind is not ("equipment" or "stackable")) throw new AuctionFault("invalid_cn_item_kind");
            if (items.ContainsKey(id)) throw new AuctionFault("duplicate_cn_item_id");
            bool named = ValidName(row.Name);
            string name = named ? row.Name!.Trim() : Missing(id);
            string category = row.Kind == "equipment" ? "装备" : "道具";
            var aliases = row.SearchAliases ?? [];
            if (aliases.Length > 16 || aliases.Any(a => string.IsNullOrWhiteSpace(a) || a.Length > 128 || a.Any(char.IsControl)))
                throw new AuctionFault("invalid_cn_search_alias");
            // Search aliases may match, but the display name always comes from CN.
            string text = Normalize(string.Join(' ', new[] { name, category }.Concat(aliases)));
            items.Add(id, new(id, new(id.ToString(CultureInfo.InvariantCulture), name, row.Kind, category, named), text));
        }
        // Also bind pagination to actual indexed content, not only caller metadata.
        revision = Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(new {
            source, rows = items.Values.Select(x => new { x.Id, x.Item, x.Text }).ToArray()
        })));
    }

    public CnSearchItem Resolve(string itemId)
    {
        uint id = Id(itemId);
        return items.TryGetValue(id, out var entry) ? entry.Item :
            new(id.ToString(CultureInfo.InvariantCulture), Missing(id), "unknown", "未分类", false);
    }

    public CnSearchPage Search(string query, int limit = 40, CnSearchCursor? cursor = null)
    {
        if (query is null || query.Length > 80 || query.Any(char.IsControl) || limit is < 1 or > 100)
            throw new AuctionFault("invalid_cn_search");
        string normalized = Normalize(query);
        string context = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(revision + "\n" + normalized + "\n" + limit)));
        if (cursor is not null && cursor.Context != context) throw new AuctionFault("cn_search_cursor_conflict");
        string[] terms = normalized.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        bool numeric = uint.TryParse(normalized, NumberStyles.None, CultureInfo.InvariantCulture, out uint exact);
        var matches = items.Values.Where(row => row.Id > (cursor?.AfterItemId ?? 0) &&
            (numeric ? row.Id == exact : terms.All(term => row.Text.Contains(term, StringComparison.Ordinal)))).Take(limit + 1).ToArray();
        var page = matches.Take(limit).Select(row => row.Item).ToArray();
        return new("zh-CN", source.ResourceFingerprint, page,
            matches.Length > limit ? new(context, matches[limit - 1].Id) : null);
    }

    private static string Missing(uint id) => $"未收录物品（{id}）";
    private static uint Id(string value)
    {
        if (!uint.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out uint result) || result == 0 ||
            result.ToString(CultureInfo.InvariantCulture) != value) throw new AuctionFault("invalid_cn_item_id");
        return result;
    }
    private static bool ValidName(string? name) => !string.IsNullOrWhiteSpace(name) && name.Length <= 512 &&
        !name.Contains('\uFFFD') && !name.Any(char.IsControl) &&
        !name.EndsWith(".equ", StringComparison.OrdinalIgnoreCase) &&
        !name.EndsWith(".stk", StringComparison.OrdinalIgnoreCase);
    private static string Normalize(string value) => string.Join(' ',
        value.Normalize(NormalizationForm.FormKC).ToUpperInvariant().Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
}

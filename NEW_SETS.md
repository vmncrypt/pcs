# Adding New Pokemon Sets

When a new Pokemon TCG set releases, follow these steps to start tracking it.

## Quick Method (Recommended)

### 1. Add the Set

```bash
python add_new_set.py "Pokemon Scarlet & Violet - Surging Sparks"
```

This creates an empty group in Supabase. You can verify with:

```bash
python add_new_set.py --list
```

### 2. Import Cards

**Option A: From BankTCG Source Data**

If you have updated `pokemon-cards-base-data.json`:

```bash
python import_pokemon_data.py
```

This imports all cards from the JSON file, including the new set.

**Option B: Manual SQL (for placeholder sets)**

```sql
-- In Supabase SQL Editor
INSERT INTO groups (name) VALUES ('Pokemon Scarlet & Violet - Surging Sparks');
```

### 3. Sync Eligible Products

Mark cards worth tracking (market_price >= $15):

```bash
python sync_eligible_products.py
```

### 4. Let Automation Run

GitHub Actions will automatically scrape graded sales every 5 days for all eligible products.

---

## Manual Card Entry

If you need to add individual cards manually:

```bash
# Coming soon: add_card.py script
# For now, use Supabase SQL Editor
```

**Example SQL:**

```sql
INSERT INTO products (
  group_id,
  variant_key,
  name,
  number,
  market_price,
  rarity
)
SELECT
  g.id,
  'sv08-199',
  'Pikachu ex - Special Illustration Rare',
  '199',
  120.00,
  'Ultra Rare'
FROM groups g
WHERE g.name = 'Pokemon Scarlet & Violet - Surging Sparks';
```

---

## Automated Scraping (Advanced)

### Bulbapedia + PriceCharting

```bash
# Note: May be blocked by Cloudflare
python scrape_new_sets.py --all --output scraped_data.json
```

If successful:
- Scrapes all sets from Bulbapedia
- Scrapes all cards from PriceCharting
- Imports directly to Supabase

### Troubleshooting

If you see 403 errors:
- Bulbapedia/PriceCharting may be blocking automated access
- Use manual methods above
- Or add Selenium support (heavyweight dependency)

---

## Workflow Summary

```
New Set Releases
    ↓
Manual: python add_new_set.py "Set Name"
    ↓
Import: python import_pokemon_data.py
    ↓
Sync: python sync_eligible_products.py
    ↓
Wait 5 days → GitHub Actions scrapes graded sales automatically
    ↓
Export: python export_to_app_format.py (when ready)
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Add new set | `python add_new_set.py "Set Name"` |
| List all sets | `python add_new_set.py --list` |
| Import cards | `python import_pokemon_data.py` |
| Sync tracking | `python sync_eligible_products.py` |
| Test single card | `python scrape_single_product.py "variant-key"` |
| Export to app | `python export_to_app_format.py` |

---

## Notes

- New sets only release every ~3 months
- Manual process takes < 5 minutes
- Automation handles all graded sales scraping
- No need to fight anti-bot measures

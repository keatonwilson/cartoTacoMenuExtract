-- Step 1: Find duplicate Maico entries and identify which est_id to keep.
SELECT est_id, name, address, created_at
FROM sites
WHERE name ILIKE '%maico%'
ORDER BY est_id;

-- Step 2: After identifying the spurious est_id from above, replace 6 below
-- with the est_id you want to DELETE, then run each block.

-- Delete child rows first (FK constraint order), then the site.
-- Replace 6 with the spurious est_id.

-- DELETE FROM descriptions WHERE est_id = 6;
-- DELETE FROM salsa      WHERE est_id = 6;
-- DELETE FROM hours      WHERE est_id = 6;
-- DELETE FROM protein    WHERE est_id = 6;
-- DELETE FROM menu       WHERE est_id = 6;
-- DELETE FROM sites      WHERE est_id = 6;

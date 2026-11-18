# Elements

## Importing and Exporting

Use the **Import** and **Export** buttons on the Elements admin changelist. Exports include each Element's `id`, `parent_element`, and `name`.

The `id` column is required in import files and identifies which Element to update. A row with a blank `id` creates a new Element, even if its name already exists; a file without an `id` column is rejected.

Enter `parent_element` as the parent's exact name, not its numeric ID. If that parent name does not exist, importing the row creates it.

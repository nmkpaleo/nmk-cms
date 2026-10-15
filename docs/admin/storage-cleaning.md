# Storage cleaning and merging

The Storage admin list at `/admin/cms/storage/` includes **Clean and merge Storage values** for staff users with Storage change permission and for superusers.

## Supported values

The cleaner normalizes supported storage labels into a common form:

- `AA11` and `AA 1/1` become `AA 11`;
- `08AF` and `08 AF` become `08 AF`;
- `81 G/F` becomes `81 GF`;
- `35 AB` remains `35 AB`.

Numeric-first labels use exactly two digits followed by two letters. Pipe-delimited values are normalized individually, duplicate normalized values are removed, and the remaining values are joined with ` | `. For example, `08AF | 08 AF` becomes `08 AF`, while `AA11 | AA 1/2` becomes `AA 11 | AA 12`.

Values that do not match a supported format, such as `On a table`, are omitted from processing and listed in the preview and result report. They are not deleted or changed.

## Parents and relations

The preview lists the original values, normalized value, and parent information before applying changes. When a group has one meaningful parent, it is retained for the merged record. Empty parents and `-Undefined` are treated as no meaningful parent; after merging, the group uses the Storage record named `-Undefined` as its parent.

If a group has multiple meaningful parents, the user must choose the parent before that group can be processed. The cleaner does not silently choose between conflicting parents.

All Storage foreign-key relations are reassigned to the surviving record through the merge engine. The operation runs transactionally and produces merge/history audit records. The result page reports groups processed, records merged, relations reassigned, omitted values, and the original-to-normalized mappings.

Review the preview carefully before selecting **Apply clean and merge**. Use a staging or backup database for the first run on a large catalogue.

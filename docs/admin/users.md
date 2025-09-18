# Users (Admin)

Use the Django administration site to create accounts and control what each person can do in the collections management system.

## Adding a new user

1. Sign in to the Django admin and open **Users** under **Authentication and Authorization**.
2. Select **Add user**.
3. Enter a unique **Username** and an initial **Password**, then choose **Save and continue editing** to open the full profile form.
4. Fill in the person’s name and email details. Leave **Active** checked so the account can sign in. Enable **Staff status** only if the user needs access to the admin itself, and reserve **Superuser status** for system maintainers.
5. Choose **Save** when you are finished.

## Assigning the user to a group

Group membership controls which features appear for the user inside the site.

1. Open the user record you just created (or any existing account) in the Django admin.
2. Scroll to the **Permissions** section.
3. Use the **Groups** selector to move the appropriate roles into the **Chosen groups** list. Hold `Ctrl` (or `Cmd` on macOS) to select multiple entries.
4. Select **Save** to apply the changes.

### Common groups

- **Collection Managers** – unlocks tools for managing drawers, creating accessions, and uploading scans.
- **Curators** – grants read access to unpublished accession content for review.
- **Interns** – limits the dashboard to scanning tasks so interns can start and stop drawer sessions.
- **Preparators** – allows preparators to record and update preparation work.

Refer to the [User Rights](../user-rights.md) guide for a complete summary of the capabilities each role provides.

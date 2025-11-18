# Accession Number Series (Admin)

Accession number series issue sequential specimen numbers to individual users. Each series tracks the next number that will be assigned when a collection manager generates accessions, and only one active series is allowed per user at a time. Series created for the organisation user **TBI** use a dedicated numbering pool that starts at one million; every other user shares a pool that starts at one.

## Creating a series

1. Sign in to the Django admin and open **Accession number series**.
2. Select **Add accession number series**.
3. Choose the user the range belongs to. The form pre-populates **Start from** and **Current number** with the next available number for that user’s pool.
4. Enter the **Count** of accession numbers you want to allocate. The live preview beneath the field shows the exact range that will be generated before you save.
5. Leave **Is active** checked so the user can draw from the new range, then choose **Save**.

When the record is saved the system calculates the **End at** value automatically. Existing series entries become read-only so the allocation history stays intact.

### Creating a series from the dashboard

Collection managers and superusers can also start a new series directly from the CMS dashboard by choosing **Generate batch** in the Collection management card. The shortcut is disabled for collection managers who already have an active series so they finish their current range before requesting more; superusers can always access the form.

1. Open the dashboard and select **Generate batch**. If you are a collection manager with an active series you will see a note explaining that the action is unavailable until the active range is exhausted.
2. The form hides the **User** field and auto-assigns it to the signed-in user. **Start from** and **Current number** are prefilled and read-only based on the correct numbering pool (the dedicated “TBI” pool or the shared pool for everyone else).
3. Enter the **Count** of numbers to allocate (up to 100). Other fields such as collection or specimen prefix remain optional or hidden to mirror the admin add view defaults.
4. Submit the form to create the series and jump to the **Accession wizard**, where the new numbers are immediately available for accession creation.

## Monitoring usage

Whenever accession numbers are generated for the assigned user, the series automatically advances its **Current number**. You can review the remaining numbers by comparing **Current number** and **End at**, or open the history tab in the admin to see when the range changed. When the final number in the range is used the system marks the series as inactive for you.

Collection managers see shortcuts to create single accessions or batches only when they have an active series, so removing access will hide those options from their dashboard.

## Starting a new range for a user

1. Open the user’s existing accession number series from the admin list.
2. Confirm the current range has been fully used and is now marked inactive. Only one active range is allowed per user, so wait for the current numbers to be exhausted before issuing more.
3. Add a new series for the same user. The form again proposes the next available number—either right after the previous shared pool range or, for TBI’s dedicated pool, immediately after the last issued number.
4. Save the record to activate the new range.

Deactivate any old series as soon as the numbers are exhausted. This prevents overlapping ranges and ensures the correct counts are displayed to collection managers while they work.

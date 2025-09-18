# Scanning

The scanning workflow links assigned drawers to timed scanning sessions so that managers and interns can coordinate digitization work.

## Roles and access

### Collection Managers
- Maintain drawer records and choose the correct scanning status for each drawer. When a drawer is set to *In progress*, managers must select the interns who will scan it.【F:docs/user/drawer-register.md†L3-L14】
- Review drawer details to monitor the log of every scanning session and confirm when work is finished.【F:app/cms/templates/cms/drawerregister_detail.html†L12-L32】

### Interns
- See a **My Drawers** table on the dashboard listing only drawers that are marked *In progress* and assigned to them, including any active timer for work already underway.【F:app/cms/views.py†L269-L285】【F:app/cms/templates/cms/dashboard.html†L141-L205】
- Start and stop scanning sessions from the dashboard buttons. The **Start scanning task** button is disabled whenever a session is already running, and the **Stop scanning task** button is disabled until a session has begun.【F:app/cms/templates/cms/dashboard.html†L178-L185】

## Preparing a drawer for scanning (Collection Managers)
1. Open the Drawer Register and create or edit the drawer that needs to be scanned.【F:docs/user/drawer-register.md†L5-L22】
2. Change the scanning status to *In progress* and select one or more interns in the **Scanning users** field. Save the drawer to publish the assignment.【F:docs/user/drawer-register.md†L9-L18】【F:app/cms/models.py†L1166-L1178】
3. Update the status to *Scanned* once the scans have been reviewed so the drawer no longer appears in intern dashboards.【F:app/cms/models.py†L1166-L1174】

## Running a scanning session (Interns)
1. Sign in and open the dashboard. The **My Drawers** table shows every drawer you have been assigned that is currently in progress.【F:app/cms/views.py†L269-L285】【F:app/cms/templates/cms/dashboard.html†L141-L176】
2. Click **Start scanning task** when you begin scanning. The system records the start time and displays a live timer while the session is active.【F:app/cms/views.py†L1431-L1437】【F:app/cms/templates/cms/dashboard.html†L164-L204】
3. Click **Stop scanning task** as soon as you finish with the drawer. The timer stops and the end time is saved to the scan log for managers to review.【F:app/cms/views.py†L1439-L1451】【F:app/cms/templates/cms/drawerregister_detail.html†L12-L27】
4. If further work is needed later, repeat the start/stop process. Each pair of actions creates a new entry in the drawer’s scan history, ensuring the project tracks how long each session lasted.【F:app/cms/views.py†L1431-L1451】【F:app/cms/templates/cms/drawerregister_detail.html†L12-L32】

## Monitoring progress (Collection Managers)
- Use the drawer detail page to review who scanned the drawer and how long each session lasted before approving the work or updating the status.【F:app/cms/templates/cms/drawerregister_detail.html†L12-L32】
- Adjust assignments or statuses as needed so that only active tasks remain visible to interns on the dashboard.【F:docs/user/drawer-register.md†L9-L22】【F:app/cms/views.py†L269-L285】

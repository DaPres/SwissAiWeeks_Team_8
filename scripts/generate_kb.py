"""Regenerates kb/*.md (synthetic knowledge base, ~26 short articles). Run: python scripts/generate_kb.py

The KB is SYNTHETIC and written for this event (no real Swiss Life documentation was provided);
every article carries ``synthetic: true`` and the README says so.
"""
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "kb"

ARTICLES = [
    ("KB-01", "Trading Platform - incident handling", "[Trading Platform]", "procedure", """## When to use
Front-office trading application problems: trade capture or entry failing, execution venue / market connectivity or FIX session drops, trader screens frozen or blotter not updating.
## First checks
1. Confirm scope: one trader, one desk or all users; which venues or FIX sessions are affected.
2. Check the platform health dashboard and the last deployment or configuration change.
3. Check whether Order Management and Trade Matching downstream flows are still receiving messages.
## Standard resolution paths
- Restart the failed FIX session or connector, then replay queued messages after confirming no duplicates.
- Roll back the last configuration or reference-data change if the fault started right after it.
## Requester reply points
- The trading support team has been notified and is checking connectivity and the latest changes.
- Please tell us which desks and venues are affected and the exact time the problem started.
## Analyst next steps
- Confirm business impact with the desk head before market open or close.
- Correlate with open incidents on Order Management and Trade Matching.
- Escalate to the platform vendor if the fault persists after a connector restart.
"""),
    ("KB-02", "Order Management - stuck or misrouted orders", "[Order Management]", "procedure", """## When to use
Orders that stay in a pending or approval state, do not reach execution routing, or are sent down the wrong broker path; also failures after a broker or clearing account change.
## First checks
1. Reproduce with one new order and note the status it stops at.
2. Compare the broker account, clearing account and routing table entries with the last approved setup.
3. Check whether orders can be released manually and whether traders have a working workaround.
## Standard resolution paths
- Correct the broker routing or account mapping table, test with a single order, then release held orders.
- Re-run the approval workflow step that failed once the mapping is valid.
## Requester reply points
- Order management support is reviewing the routing configuration for the affected broker account.
- Please share two or three example order references and the time of the account change.
## Analyst next steps
- Verify pre-trade compliance rules are not the cause of the held status.
- Notify the trading desk when held orders have been released.
- Record the corrected mapping in the change log.
"""),
    ("KB-03", "Trade Matching - rejected allocations and matching backlog", "[Trade Matching]", "procedure", """## When to use
Allocation or confirmation messages rejected by a matching adapter, unmatched trades accumulating, broker confirmations that cannot be paired with staged allocations.
## First checks
1. Identify the adapter, the broker and the number of rejected messages and their error codes.
2. Compare execution references and allocation details with the broker message; check standing settlement instruction (SSI) and account setup.
3. Check whether the backlog is growing or stable.
## Standard resolution paths
- Complete or correct the broker account setup or SSI mapping, then replay the rejected messages.
- Reprocess the batch and validate that all affected trades reach matched status.
## Requester reply points
- The matching team is analysing the rejected messages and will replay them once the mapping is confirmed.
- Please send the broker name, adapter name and a sample of the rejected references.
## Analyst next steps
- Confirm the confirmation workflow is unblocked for the affected trades.
- Warn Securities Settlement if unmatched trades approach settlement date.
- Correlate repeated rejections from the same broker.
"""),
    ("KB-04", "Securities Settlement - status messages, custodian delays and queue backlog", "[Securities Settlement]", "procedure", """## When to use
Delayed or missing settlement status messages (for example MT536 or MT548 style statements), settlement confirmation or acknowledgement queues backing up, custodian or CSD notices about delays, settlement fails.
## First checks
1. Determine whether the delay is on the custodian side, in our middleware or in the operations dashboard.
2. Check queue depth, consumer health and the age of the oldest unprocessed message.
3. Identify trades close to intended settlement date and possible penalty exposure.
## Standard resolution paths
- Restart a stalled message consumer, replay the pending messages and confirm downstream custody records catch up.
- If the custodian is late, pause automated fail-chasing, wait for the statements and reconcile the backlog once they arrive.
## Requester reply points
- Securities operations is checking the settlement message flow and custodian statements.
- Please list affected trades or accounts and the custodian involved.
## Analyst next steps
- Track custodian ETA and notify affected desks.
- Reconcile custody positions against settlement instructions after messages resume.
- Escalate to middleware support if the queue keeps growing after a listener restart.
"""),
    ("KB-05", "Corporate Actions - event ingestion and option codes", "[Corporate Actions]", "procedure", """## When to use
Corporate action events loaded incompletely, missing mandatory fields such as option codes, elections that cannot be published to the operations screen, dividend or split events not booked.
## First checks
1. Identify the ingestion feed, the event identifiers and how many events are incomplete.
2. Compare the payload with the vendor or custodian notification (event type, option codes, dates).
3. Check election deadlines and record dates that are close.
## Standard resolution paths
- Update the option-code mapping table, reprocess the feed and confirm the elections show correctly on the operations screen.
- Manually enrich individual events if only a few are affected, then document the change.
## Requester reply points
- The corporate actions team is correcting the event data and will confirm when elections are visible.
- Please provide the event identifiers and the election deadline.
## Analyst next steps
- Prioritise events with the nearest deadline.
- Inform portfolio managers if an election window is at risk.
"""),
    ("KB-06", "Fund Pricing - stale prices and tolerance checks", "[Fund Pricing]", "procedure", """## When to use
Prices missing, stale or outside tolerance; price validation or price mastering runs failing; a pricing source not delivering.
## First checks
1. Identify the affected securities, pricing source and valuation date.
2. Check the vendor feed delivery time against the pricing cut-off.
3. Compare the price with the previous day and with a secondary source.
## Standard resolution paths
- Re-run price validation after the corrected feed arrives; override with an approved manual price only with documented approval.
## Requester reply points
- The valuation and pricing team is validating the affected prices against the alternate source.
- Please list the securities, funds and valuation date concerned.
## Analyst next steps
- Coordinate with Market Data Services if the feed was late.
- Warn the NAV team if the pricing deadline may be missed.
"""),
    ("KB-07", "NAV Calculation - tolerance breaches and publication", "[NAV Calculation]", "procedure", """## When to use
End-of-day valuation run stopped or breached tolerance thresholds, NAV not published to downstream control queues, funds with unexpected NAV movements.
## First checks
1. Identify the funds, share classes and the run identifier; check the last successful publication.
2. Review the tolerance report to separate a genuine market move from a data error (price, FX, position, cash).
3. Check the downstream publication queue and the next accounting cycle start time.
## Standard resolution paths
- Correct the underlying price or position error, re-run the valuation and publish the NAV once tolerances are met.
- If the movement is genuine, obtain documented sign-off and release with an explanatory note.
## Requester reply points
- The valuation team is investigating the tolerance breach and will confirm before the next accounting cycle.
- Please provide the fund list and the run identifier.
## Analyst next steps
- Confirm the publication deadline with fund administration.
- Correlate with pricing and market data incidents.
"""),
    ("KB-08", "Portfolio Accounting - reconciliation and access", "[Portfolio Accounting]", "procedure", """## When to use
Position or cash reconciliation breaks, ledger or journal issues, month-end close support, requests for accounting roles or dashboard access.
## First checks
1. Identify the portfolios, accounts and period.
2. Check whether the break originates from a late trade, a corporate action or a pricing difference.
3. For access requests: confirm the role, entity and approver.
## Standard resolution paths
- Book the correcting entry with approval and re-run the reconciliation.
- Grant the standard processing role and dashboard read access after manager approval.
## Requester reply points
- The investment operations team is reviewing the reconciliation break or access request.
- Please confirm the entity, role required and the approving manager.
## Analyst next steps
- Verify segregation of duties before granting processing rights.
- Confirm to the requester once the access or correction is in place.
"""),
    ("KB-09", "Cash Management - sweeps, cut-offs and margin", "[Cash Management]", "procedure", """## When to use
Missing or unexpected cash balances, margin or collateral sweep problems, bank statement differences, cash ledger breaks, treasury movements after a cut-off.
## First checks
1. Ask for the account, currency and booking date if they are not stated.
2. Reconcile the cash ledger with the bank statement and the sweep instructions.
3. Check whether a banking cut-off was missed or a value date is wrong.
## Standard resolution paths
- Book a value-dated or intraday adjustment for a missed cut-off and confirm the balance with the treasury desk.
## Requester reply points
- The treasury team is reconciling the account with the bank statement.
- Please confirm the account, currency and the date of the affected movement.
## Analyst next steps
- Confirm liquidity requirements for the day with the desk.
- Add the account to the daily cash watch list until it is reconciled.
"""),
    ("KB-10", "Risk & Compliance Monitoring - breaches, dashboards and screening", "[Risk & Compliance Monitoring]", "procedure", """## When to use
Limit or guideline breach reporting, compliance dashboards showing stale or wrong statuses after a rule change, sanctions or AML screening, licences and access for compliance analysts.
## First checks
1. Compare the dashboard summary with the underlying rule results and the last rule deployment.
2. Confirm whether a rerun completed and whether the summary cache refreshed.
3. For access or licences: confirm the analyst role and approver.
## Standard resolution paths
- Refresh or rebuild the summary from the rule results and validate several breaches manually.
- Provision the standard compliance analyst licence or role after approval.
## Requester reply points
- The risk and controls team is checking the dashboard refresh and rule results.
- Please share example breaches and the time of the rule update.
## Analyst next steps
- Tell compliance to rely on detail pages until the summary is fixed.
- Log the issue as a control observation if a breach was mis-reported.
"""),
    ("KB-11", "Regulatory Reporting - submission and gateway rejections", "[Regulatory Reporting]", "procedure", """## When to use
Regulatory submissions (for example LEI, MiFID, EMIR, AIFMD or local regulator files) rejected by a gateway, missing mandatory fields, reporting deadlines at risk.
## First checks
1. Read the rejection message and identify the missing or invalid field and the affected records.
2. Check the master data for the entities or counterparties concerned, for example missing classification.
3. Confirm the regulatory deadline and the resubmission window.
## Standard resolution paths
- Correct the master data, regenerate the submission file and resubmit; confirm acceptance from the gateway.
## Requester reply points
- The risk and controls team is correcting the rejected data and will resubmit before the deadline.
- Please forward the full rejection message and the file name.
## Analyst next steps
- Track the regulatory deadline and escalate if resubmission is not possible in time.
- Verify other files created from the same master data.
"""),
    ("KB-12", "Rimes Data Feed - late or missing vendor files", "[Rimes Data Feed]", "procedure", """## When to use
Vendor benchmark, index or price files delivered late or incomplete, publication delayed beyond the processing window, downstream jobs started with stale input.
## First checks
1. Identify the file name, vendor, expected and actual delivery time.
2. Check which downstream jobs consumed stale input (price mastering, valuation, reporting).
3. Ask the vendor for the corrected file ETA.
## Standard resolution paths
- Once the corrected file arrives, reload it and rerun the dependent jobs; validate row counts and key prices.
## Requester reply points
- Market data services has contacted the vendor and will rerun dependent jobs when the corrected file is available.
- Please provide the file name and the jobs that consumed it.
## Analyst next steps
- Warn the pricing and NAV teams about possible stale inputs.
- Record the delay against the vendor service level.
"""),
    ("KB-13", "Client Reporting - report packs and templates", "[Client Reporting]", "procedure", """## When to use
Client report PDFs or packs generated with missing sections, wrong figures or layout problems; reports not distributed on time.
## First checks
1. Compare the generated output with the staging preview and the data source.
2. Check the template logic and recent template changes.
3. Identify which clients or entities were included in the affected batch.
## Standard resolution paths
- Fix the template condition, regenerate the batch and spot-check a sample before release.
## Requester reply points
- The client services team is fixing the report template and will regenerate the affected reports before release.
- Please send two example reports and the batch date.
## Analyst next steps
- Hold distribution of the affected batch until validated.
- Inform relationship managers if clients already received incomplete reports.
"""),
    ("KB-14", "Tax Reporting - licences, entitlements and workflow", "[Tax Reporting]", "procedure", """## When to use
Requests for tax reporting licences or access, tax pack or extract problems, withholding tax and reclaim workflows.
## First checks
1. Confirm the requester's role, entity and the workflow (for example withholding tax extracts).
2. Check that a licence is available and that the tax team lead approves.
## Standard resolution paths
- Assign the licence or standard processing entitlement and confirm the user can open the output workspace.
## Requester reply points
- The tax and reporting team is validating the request and will confirm when the licence is assigned.
- Please confirm the user, entity and business justification.
## Analyst next steps
- Track licence usage against the purchased count.
- Review inherited groups when the role changes.
"""),
    ("KB-15", "CRM & Client Portal - access and portal issues", "[CRM & Client Portal]", "procedure", """## When to use
New user access for relationship managers, portal login or permission issues, CRM data problems.
## First checks
1. Confirm the role profile (for example standard sales role), entity and line-manager approval.
2. Check that no elevated rights are requested.
## Standard resolution paths
- Assign the role-based profile, verify login and record the approval.
## Requester reply points
- The client services team will provision the standard role once the approval is confirmed.
- Please confirm the role profile and approving manager.
## Analyst next steps
- Verify access matches the entity and team.
- Close the request after the user confirms successful login.
"""),
    ("KB-16", "Identity & Access Management - deactivation and access removal", "[Identity & Access Management]", "procedure", """## When to use
Deactivating leavers or contractors, removing access after a role change, cleaning up inactive accounts, multi-factor or single sign-on problems.
## First checks
1. Confirm the list of accounts and the effective date from HR or the line manager.
2. Identify direct entitlements, group memberships, inherited and temporary rights.
3. Check linked applications and service accounts.
## Standard resolution paths
- Disable the account, remove group memberships and temporary rights, run an access review to confirm nothing remains, and record the evidence.
## Requester reply points
- Enterprise applications will remove all access for the listed accounts and confirm the result.
- Please provide the account list and effective date.
## Analyst next steps
- Run a post-removal access report and attach it to the ticket.
- Escalate to security if privileged access was involved.
"""),
    ("KB-17", "SharePoint & File Storage - permissions and offboarding", "[SharePoint & File Storage]", "procedure", """## When to use
Site or library permission changes, removal of access after offboarding, synchronized folder problems, storage quota issues.
## First checks
1. Identify the sites, libraries and groups involved.
2. Check direct permissions, group-inherited access and synchronised folders.
## Standard resolution paths
- Remove direct permissions and group memberships, unlink synchronised folders and verify with a permissions report.
## Requester reply points
- Enterprise applications will remove the access and confirm once the permissions report is clean.
- Please list the sites and the effective date.
## Analyst next steps
- Confirm the departed user no longer appears in any site permissions.
- Review guest access on the same sites.
"""),
    ("KB-18", "Outlook & Email - mailboxes, shared mailboxes and distribution lists", "[Outlook & Email]", "procedure", """## When to use
Requests for shared mailboxes or distribution lists, mail delivery problems, calendar issues, mailbox access.
## First checks
1. Distinguish a real mail outage from a provisioning request with an alarming title.
2. For provisioning: confirm owner, members, send rights and the required date.
## Standard resolution paths
- Create the shared mailbox and distribution list, grant send and access rights, and confirm visibility in Outlook.
- If the title suggested an outage but no disruption exists, reclassify as a service request first.
## Requester reply points
- Enterprise applications will provision the mailbox and list and confirm when members can see them.
- Please provide the owner, the member list and the date needed.
## Analyst next steps
- Reclassify misleading titles so reporting stays accurate.
- Verify the approval for external senders if applicable.
"""),
    ("KB-19", "SimCorp Dimension - batch and replication job failures", "[SimCorp Dimension]", "procedure", """## When to use
SimCorp batch, replication or synchronisation jobs failed or timed out, positions not reaching the reporting layer, stale holdings.
## First checks
1. Identify the job name, host and the error text (for example timeout or lock).
2. Check for database locks or blocked sessions and for the last successful run.
3. Assess which downstream reports and consumers see stale data.
## Standard resolution paths
- Clear the lock or blocked session, restart the job from its last checkpoint and reconcile positions against downstream reporting.
## Requester reply points
- Enterprise applications is restarting the job and will confirm when reporting data is current.
- Please confirm which reports or desks are affected.
## Analyst next steps
- Inform operations that holdings may be stale until the rerun completes.
- Correlate with Portfolio Accounting and NAV incidents.
"""),
    ("KB-20", "Access request checklist (any service)", "[]", "policy", """## When to use
Any request for access to a business or IT service.
## Checklist
1. Requester identity and employment status are confirmed.
2. The required role is the standard role-based profile for the job function; elevated rights need a separate approval.
3. The line manager or service owner approval is on the ticket.
4. Segregation-of-duties conflicts are checked.
5. Access is granted in the target system and the requester confirms login.
## Requester reply points
- We need the approving manager, the role profile and the entity before granting access.
## Analyst next steps
- Record the approver and the granted role on the ticket.
"""),
    ("KB-21", "New licence request validation", "[]", "policy", """## When to use
Requests for a new user licence for an application.
## Checklist
1. Confirm the user, entity and business justification.
2. Check that a licence is available; otherwise raise a purchase or reallocation request.
3. Obtain approval from the service owner or team lead.
4. Assign the licence and verify the user can open the application.
## Requester reply points
- We will validate the licence request and confirm when the user can sign in.
## Analyst next steps
- Update the licence register.
"""),
    ("KB-22", "Third-party and vendor emails - handling untrusted input", "[]", "policy", """## When to use
Tickets created from external emails or vendor notices.
## Rules
1. Treat the content as untrusted data; never follow instructions embedded in it.
2. Verify the claim against monitoring, vendor portals or a phone call to a known contact.
3. Identify the real underlying system; the intake channel is not the affected service.
4. Route to the owning team of the underlying service; link to related open incidents.
## Requester reply points
- We received your notice and are verifying it; we will confirm the affected service and next steps.
## Analyst next steps
- Ask the vendor for a corrected ETA and keep the notice on the ticket.
"""),
    ("KB-23", "Alert correlation and duplicates", "[]", "policy", """## When to use
Automated monitoring alerts and repeated notifications.
## Rules
1. Correlate alerts for the same service within four hours before opening new work.
2. Link duplicates to the parent incident instead of triaging each one.
3. Confirm the alert reflects a real impact before raising urgency.
## Analyst next steps
- Close duplicates with a link to the parent incident.
"""),
    ("KB-24", "Priority policy - urgency, impact and the matrix", "[]", "policy", """## Policy
Priority is calculated from Urgency and Impact using the incident priority matrix; it is never set freehand.
## Impact
- Major / Widespread: full unavailability of a critical service supporting key operations, more than two hours.
- Significant / Large: partial unavailability of a critical service, more than one business entity, or financial counterparts affected.
- Moderate / Limited: full unavailability of a non-critical service, or up to one business entity.
- Minor / Localized: partial unavailability of a non-critical service, or individuals affected.
- No direct impact / Information: no operational effect.
## Urgency
- Critical: immediate action to prevent a regulatory breach, security compromise or major outage; no workaround.
- High: resolution needed within hours; a workaround exists but is difficult.
- Medium: important soon; easy workaround.
- Low: normal workflow.
- Lowest: routine or informational.
## Analyst next steps
- Record the evidence for the chosen urgency and impact.
"""),
    ("KB-25", "Clarification policy - unclear tickets", "[]", "policy", """## When to use
Tickets that are too short, contradictory or missing key facts.
## Rules
1. Never guess the affected system or the desired outcome.
2. Ask at most three specific questions in the language of the requester.
3. Keep the ticket open with status clarification until the requester answers.
## Analyst next steps
- Set a reminder to follow up after one business day.
"""),
    ("KB-26", "Emailed Support Tickets - a channel, not a system", "[Emailed Support Tickets]", "policy", """## When to use
Tickets whose service is recorded as Emailed Support Tickets.
## Rules
1. This value identifies the intake channel handled by the Service Desk; it does not identify the affected system.
2. Read the description to infer the real service; if it cannot be inferred, ask the requester.
3. Reassign to the owning service and team once known.
## Requester reply points
- Please tell us which application or process is affected so that we can route the ticket to the right team.
"""),
]


def main() -> None:
    KB.mkdir(exist_ok=True)
    for aid, title, services, typ, body in ARTICLES:
        (KB / f"{aid}.md").write_text(
            f"---\nid: {aid}\ntitle: {title}\nservices: {services}\ntype: {typ}\nsynthetic: true\n---\n# {title}\n\n{body}",
            encoding="utf-8",
        )
    print(f"{len(ARTICLES)} articles written to {KB}")


if __name__ == "__main__":
    main()

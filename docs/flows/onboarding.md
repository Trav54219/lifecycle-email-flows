# Flow spec: Post-purchase Onboarding

> **Modeled, not deployed.** This spec is generated from `flows/onboarding.json` in this repo and laid out in the style of a Klaviyo flow / Braze Canvas export. It has never been imported into, or run on, any of those products.

For first-time buyers only. A tips email, then a second email chosen by whether they clicked anything since their first order.

## Entry and exit

| Setting | Value |
|---|---|
| Trigger event | `placed_order` |
| Trigger filter | count of `placed_order` == 1 |
| Re-entry | once per customer |
| Exit events | none |
| Sends to dormant tier | no (sunset policy applies) |

## Steps

| Step | Type | Detail | Next |
|---|---|---|---|
| `wait_3d` | delay | Wait 3 days | `send_1_tips` |
| `send_1_tips` | send | Send: onboarding_1_tips (subject: `Getting the most from your first order`) | `wait_4d` |
| `wait_4d` | delay | Wait 4 days | `clicked` |
| `clicked` | branch | Split: customer did `email_click` since entering the flow | yes -> `send_2_referral`, no -> `send_2_help` |
| `send_2_referral` | send | Send: onboarding_2_referral (subject: `Give a friend {{ offer.discount_pct }}% off`) vars: discount_pct=10, discount_code=FRIEND10 | `end` |
| `send_2_help` | send | Send: onboarding_2_help (subject: `Anything we can help with?`) | `end` |
| `end` | exit | End | end |

## Canvas

```mermaid
flowchart TD
  T([Trigger: placed_order]) --> wait_3d
  wait_3d["Wait 3 days"]
  wait_3d --> send_1_tips
  send_1_tips["Send: onboarding_1_tips"]
  send_1_tips --> wait_4d
  wait_4d["Wait 4 days"]
  wait_4d --> clicked
  clicked{"Split: customer did email_click since entering the flow"}
  clicked -->|yes| send_2_referral
  clicked -->|no| send_2_help
  send_2_referral["Send: onboarding_2_referral"]
  send_2_referral --> end
  send_2_help["Send: onboarding_2_help"]
  send_2_help --> end
  end["End"]
```

## Delivery rules applied to every send (global policy)

- Frequency caps across all flows: max 2 per 24h, max 4 per 168h. A capped send is skipped, and the flow continues.
- Quiet hours: no sends between 21:00 and 8:00 customer-local time; the send is deferred to the end of the window and re-checked then.
- Suppressed always: unsubscribed, hard-bounced, no marketing consent.
- Sunset: tiers dormant are skipped unless the flow allows them.
- Exit events are checked before every step, including a send that was deferred.

## Rough platform mapping

| This engine | Klaviyo | Braze Canvas | Marketo |
|---|---|---|---|
| trigger event | metric-triggered flow | action-based entry | smart campaign trigger |
| delay | time delay | delay step | wait step (flow action) |
| branch | conditional split | decision split | choice step |
| send | email action | message step | send email |
| exit events | flow filter / exit on conversion | exit criteria | smart list filter in flow |
| re-entry | re-entry setting | entry re-eligibility window | "each person can run through the flow" |

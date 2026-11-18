# Flow spec: Win-back

> **Modeled, not deployed.** This spec is generated from `flows/winback.json` in this repo and laid out in the style of a Klaviyo flow / Braze Canvas export. It has never been imported into, or run on, any of those products.

Enrolls on every order; any later order cancels the earlier enrollments, so only the customer's latest order reaches day 45 with no repurchase. Two touches, soft for strong segments, offer for the rest. Dormant customers are allowed in (that is the point).

## Entry and exit

| Setting | Value |
|---|---|
| Trigger event | `placed_order` |
| Trigger filter | none |
| Re-entry | every trigger event |
| Exit events | `placed_order` |
| Sends to dormant tier | yes |

## Steps

| Step | Type | Detail | Next |
|---|---|---|---|
| `wait_45d` | delay | Wait 45 days | `split_value` |
| `split_value` | branch | Split: (customer is in segment `champions` OR customer is in segment `loyal`) | yes -> `send_1_soft`, no -> `send_1_offer` |
| `send_1_soft` | send | Send: winback_1_soft (subject: `It has been a while, {{ customer.first_name \| default: 'friend' }}`) | `wait_14d` |
| `send_1_offer` | send | Send: winback_1_offer (subject: `We saved {{ offer.discount_pct }}% for you`) vars: discount_code=MISSYOU15, discount_pct=15 | `wait_14d` |
| `wait_14d` | delay | Wait 14 days | `send_2_final` |
| `send_2_final` | send | Send: winback_2_final (subject: `Should we keep emailing you?`) | `end` |
| `end` | exit | End | end |

## Canvas

```mermaid
flowchart TD
  T([Trigger: placed_order]) --> wait_45d
  wait_45d["Wait 45 days"]
  wait_45d --> split_value
  split_value{"Split: (customer is in segment champions OR customer is in segment loyal)"}
  split_value -->|yes| send_1_soft
  split_value -->|no| send_1_offer
  send_1_soft["Send: winback_1_soft"]
  send_1_soft --> wait_14d
  send_1_offer["Send: winback_1_offer"]
  send_1_offer --> wait_14d
  wait_14d["Wait 14 days"]
  wait_14d --> send_2_final
  send_2_final["Send: winback_2_final"]
  send_2_final --> end
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

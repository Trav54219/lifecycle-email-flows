# Flow spec: Welcome Series

> **Modeled, not deployed.** This spec is generated from `flows/welcome.json` in this repo and laid out in the style of a Klaviyo flow / Braze Canvas export. It has never been imported into, or run on, any of those products.

Three-touch series for new subscribers. Branches on purchase and on engagement tier; stops pushing the incentive to buyers.

## Entry and exit

| Setting | Value |
|---|---|
| Trigger event | `signup` |
| Trigger filter | none |
| Re-entry | once per customer |
| Exit events | none |
| Sends to dormant tier | no (sunset policy applies) |

## Steps

| Step | Type | Detail | Next |
|---|---|---|---|
| `send_1` | send | Send: welcome_1 (subject: `Welcome to {{ brand.name }}, {{ customer.first_name \| default: 'there' }}`) | `wait_2d` |
| `wait_2d` | delay | Wait 2 days | `bought_1` |
| `bought_1` | branch | Split: customer did `placed_order` since entering the flow | yes -> `end`, no -> `split_engagement` |
| `split_engagement` | branch | Split: customer is in segment `highly_engaged` | yes -> `send_2_story`, no -> `send_2_incentive` |
| `send_2_story` | send | Send: welcome_2_story (subject: `How {{ brand.name }} picks what we sell`) | `wait_3d` |
| `send_2_incentive` | send | Send: welcome_2_incentive (subject: `{{ offer.discount_pct }}% off your first order`) vars: discount_code=WELCOME10, discount_pct=10 | `wait_3d` |
| `wait_3d` | delay | Wait 3 days | `bought_2` |
| `bought_2` | branch | Split: customer did `placed_order` since entering the flow | yes -> `end`, no -> `send_3` |
| `send_3` | send | Send: welcome_3_last_call (subject: `Your welcome code expires soon`) vars: discount_code=WELCOME10, discount_pct=10 | `end` |
| `end` | exit | End | end |

## Canvas

```mermaid
flowchart TD
  T([Trigger: signup]) --> send_1
  send_1["Send: welcome_1"]
  send_1 --> wait_2d
  wait_2d["Wait 2 days"]
  wait_2d --> bought_1
  bought_1{"Split: customer did placed_order since entering the flow"}
  bought_1 -->|yes| end
  bought_1 -->|no| split_engagement
  split_engagement{"Split: customer is in segment highly_engaged"}
  split_engagement -->|yes| send_2_story
  split_engagement -->|no| send_2_incentive
  send_2_story["Send: welcome_2_story"]
  send_2_story --> wait_3d
  send_2_incentive["Send: welcome_2_incentive"]
  send_2_incentive --> wait_3d
  wait_3d["Wait 3 days"]
  wait_3d --> bought_2
  bought_2{"Split: customer did placed_order since entering the flow"}
  bought_2 -->|yes| end
  bought_2 -->|no| send_3
  send_3["Send: welcome_3_last_call"]
  send_3 --> end
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

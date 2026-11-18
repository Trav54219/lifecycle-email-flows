# Flow spec: Abandoned Cart

> **Modeled, not deployed.** This spec is generated from `flows/abandoned_cart.json` in this repo and laid out in the style of a Klaviyo flow / Braze Canvas export. It has never been imported into, or run on, any of those products.

Two reminders after a cart is started. Exits the moment an order is placed. Carts under $20 do not enter. Loyal customers get no discount.

## Entry and exit

| Setting | Value |
|---|---|
| Trigger event | `added_to_cart` |
| Trigger filter | trigger event property `total` >= 20 |
| Re-entry | after 3 days |
| Exit events | `placed_order` |
| Sends to dormant tier | no (sunset policy applies) |

## Steps

| Step | Type | Detail | Next |
|---|---|---|---|
| `wait_1h` | delay | Wait 1 hour | `send_1` |
| `send_1` | send | Send: cart_reminder_1 (subject: `{{ customer.first_name \| default: 'Hi' }}, you left something in your cart`) | `wait_24h` |
| `wait_24h` | delay | Wait 1 day | `split_loyalty` |
| `split_loyalty` | branch | Split: (customer is in segment `champions` OR customer is in segment `loyal`) | yes -> `send_2_reminder`, no -> `send_2_incentive` |
| `send_2_reminder` | send | Send: cart_reminder_2 (subject: `Still thinking it over?`) | `end` |
| `send_2_incentive` | send | Send: cart_reminder_2_incentive (subject: `{{ offer.discount_pct }}% off what is in your cart`) vars: discount_code=COMEBACK5, discount_pct=5 | `end` |
| `end` | exit | End | end |

## Canvas

```mermaid
flowchart TD
  T([Trigger: added_to_cart]) --> wait_1h
  wait_1h["Wait 1 hour"]
  wait_1h --> send_1
  send_1["Send: cart_reminder_1"]
  send_1 --> wait_24h
  wait_24h["Wait 1 day"]
  wait_24h --> split_loyalty
  split_loyalty{"Split: (customer is in segment champions OR customer is in segment loyal)"}
  split_loyalty -->|yes| send_2_reminder
  split_loyalty -->|no| send_2_incentive
  send_2_reminder["Send: cart_reminder_2"]
  send_2_reminder --> end
  send_2_incentive["Send: cart_reminder_2_incentive"]
  send_2_incentive --> end
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

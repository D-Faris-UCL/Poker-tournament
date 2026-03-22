# UCL Poker AI Tournament Structure

## Overview

The tournament is a **No-Limit Texas Hold'em** competition played across two stages: a **Qualifying Layer** and a **Final Table**. All tables are 9-handed, with a starting stack of **2,000 chips**.

---

## Stage 1: Qualifying Layer

### Table Setup

- Each qualifying table seats exactly **9 players**
- Real human participants are **distributed equally** across all qualifying tables
- The remaining seats at each table are filled with **fish bots** — weak, exploitable AI bots designed to create a dynamic, realistic poker environment
- The number of qualifying tables is determined by the number of human participants:

| Human Players | Tables | Humans per Table | Fish Bots per Table |
|:---:|:---:|:---:|:---:|
| 9 | 1 | 9 | 0 |
| 18 | 2 | 9 | 0 |
| 10–17 | 2 | 5–9 | 0–4 |
| ... | ... | ... | ... |

> **General rule:** `num_tables = ceil(num_humans / 9)`, humans are spread as evenly as possible, and remaining seats are filled with fish bots.

### Blind Schedule

All qualifying tables share the same blind schedule. Blinds increase every fixed number of hands to apply pressure and ensure tables progress at a reasonable pace.

| Round | Small Blind | Big Blind |
|:---:|:---:|:---:|
| 1 | 10 | 20 |
| 50 | 20 | 50 |
| 100 | 50 | 100 |
| 150 | 100 | 200 |

> The organiser may adjust this schedule before the tournament day.

### Elimination & Advancement

- Tables play continuously until a target number of **human players have been eliminated**
- Fish bots that bust out are **not replaced**
- Human players that bust out are **eliminated from the tournament**
- Play continues until the required number of human survivors has been reached

> **Example:** If 18 humans play across 2 tables and the final table seats 9, then 9 humans must be eliminated across both tables before Stage 2 begins.

> **Note:** The exact number of survivors advancing to the final table is set by the organiser prior to the tournament.

### Fish Bots

Fish bots are provided by the tournament organisers. They are intentionally weak and are included to:

- Fill tables to a full 9 seats
- Provide exploitable opponents for skilled bots to accumulate chips against
- Create a realistic, multi-player poker environment

Fish bots are **not eligible to advance** to the final table, regardless of their chip count.

---

## Stage 2: The Final Table

### Setup

- All surviving human bots advance to a **single final table**
- Each player's chip stack is **normalised** at the start of the final table so that the **average stack is 2,000 chips**
  - Each player's stack is divided by the average qualifying stack, then multiplied by 2,000
  - Players who performed better in qualifying will start the final table with more than 2,000 chips; those who performed worse will start with fewer
  - Formula: `final_stack = (qualifying_stack / average_qualifying_stack) × 2,000`

> Chip normalisation preserves the relative chip advantage earned during qualifying while keeping stack sizes manageable for the final table.

### Blind Schedule

The final table uses an **accelerated blind schedule** to ensure the tournament concludes within the allotted time. The specific schedule will be announced by the organiser.

### Victory Condition

- Play continues until only **one player remains**
- The last human bot standing is declared the **tournament winner**

---

## Summary Flow

```
All Human Bots
      │
      ▼
┌─────────────────────────────────┐
│        STAGE 1: Qualifying      │
│  9-handed tables (+ fish bots)  │
│  Starting stack: 2,000 chips    │
│  Play until Y humans eliminated │
└────────────────┬────────────────┘
                 │  Top X humans advance
                 ▼
┌─────────────────────────────────┐
│       STAGE 2: Final Table      │
│  9-handed, humans only          │
│  Stacks normalised to 2,000     │
│  Play until 1 player remains    │
└─────────────────────────────────┘
                 │
                 ▼
           🏆 Winner
```

---

## Configuration Reference

The following parameters are set by the organiser prior to the tournament:

| Parameter | Description |
|---|---|
| `num_humans` | Total number of human bots competing |
| `num_tables` | Number of qualifying tables |
| `survivors` | Number of humans advancing to the final table (X) |
| `eliminations` | Number of humans to eliminate in qualifying (Y = num_humans − X) |
| `starting_stack` | 2,000 chips (fixed) |
| `qualifying_blinds` | Blind schedule for Stage 1 |
| `final_blinds` | Blind schedule for Stage 2 |


---

## Technical Notes

- All tables run in **restricted mode** (`restricted=True`) during the official tournament to ensure sandboxed, fair execution
- Each bot is subject to a **3-second decision time limit** and **500MB memory limit**
- Invalid actions are automatically corrected per the rules described in `README.md`
- Bots may use state accumulated during qualifying hands when playing at the final table, as long as it was stored in memory within their bot instance


---

## Live Showdown

📅 Date: Thursday, 26th March

🕰️ Time: 5:30 pm - 8:30 pm

📍 Location: Roberts Building, 421

Bot submission: https://tinyurl.com/bdfre4wt

Deadline - 22nd March, 23:59
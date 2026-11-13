---
title: Welcome to BoxUp
summary: What BoxUp is, where its data comes from, and what we plan to write about here.
date: 2026-11-03
tag: Announcement
---

BoxUp is an open source Formula 1 analytics platform. It lets you explore race sessions, qualifying telemetry, tyre strategy and race predictions, using public motorsport data and deterministic analysis tools.

## What you will find on this blog

- **Build notes.** How the ingestion pipeline, the telemetry views and the prediction model are put together.
- **Race breakdowns.** Corner by corner comparisons and stint analysis from real sessions.
- **Using the Pitwall agent.** How questions become tool calls, and how the evidence behind an answer is checked.

## Where the data comes from

Session data is ingested with FastF1, and the project also draws on OpenF1 and Jolpica for results and calendar information. The analysis you see in the app is computed from that stored data.

## Follow along

The code is on [GitHub](https://github.com/SheerWill007/Formula-I). If you want to run it yourself, the README walks through the setup.

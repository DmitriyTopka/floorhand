# Security notes

## Pairing codes: chosen trade-off

Glasses pair with a six-digit code typed into the shop bot. Automated reviews during build week raised eight findings here, several asking for opposite things (refuse when full vs evict; cap the retired list vs never drop it early; global limit vs per-address only). The rules that hold now:

- a code is single use and lives 10 minutes;
- one address (an IPv6 /64 counts as one) holds at most 20 pending codes;
- when 500 codes are pending, the oldest code of the busiest address goes;
- an evicted number is never reissued during its 10 minutes;
- at most 60 new codes a minute across the server.

Known residual risk: an attacker with many addresses can make pairing slow for a minute at a time. Nobody can pair someone else's glasses, read another person's questions, or send a reply. For a demo bot with a handful of users we accept that and stop here.

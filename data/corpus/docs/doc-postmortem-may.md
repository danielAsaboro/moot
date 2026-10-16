# Postmortem: export saturation

Date: 2026-05-12  
Author: Marcus Chen

Root cause: unbounded exports per tenant. Action items: rate limit, worker autoscaling, alerting on queue depth.

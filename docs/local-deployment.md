# Local deployment

Stage 2 provides a local development setup only. The intended local production
shape is PostgreSQL and Django on a shop computer, with the React application
served to shop browsers over the local network. Local POS use should not depend
on internet access.

Production server configuration, static asset serving, network access policy,
and installation automation remain future work. Keep machine-specific
configuration and credentials outside the repository.

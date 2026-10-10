# Frontend security regression tests

Run `npm test` from `frontend`. These tests use Node's test runner, the project's
installed TypeScript/React, and Playwright with Microsoft Edge. No application
server, credentials, or database is used: `http://app.test` and its API requests
are intercepted by the browser harness. The API/client code and React rendering,
including SSR hydration, are real; Next navigation and the HTTP responses are
controlled test boundaries.

If Playwright is supplied by an external runtime rather than installed in this
project, set `NODE_PATH` to that runtime's `node_modules` directory before running
the tests. No dependency installation is required in the prepared workspace.

Coverage includes login return URLs; identity changes, logout, token refresh and
out-of-order responses; 401/403 handling; server hydration; bounded personal and
admin pagination; unfinished review status access; explicit edition context;
and Shanghai date/expiry boundaries.

Monitoring
************

To monitor the health of the system it is a good idea to check that the frontend serving the static parts of the UI
functions and returns 200-series responses to GET requests.

The best place to monitor the back-end API with a simple GET is listing public variables, currently found at
api/v1/config. The result should be valid JSON and it should contain keys set in the database.

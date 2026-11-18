# Cedar Loop hiking-club pilot brief

Cedar Loop is a responsive web app for one local hiking club to coordinate
day hikes. The pilot is limited to 40 club members. A trip organizer creates
and manages trips; a member browses upcoming trips and responds yes or no.

Each trip records its title, date and start time, trail name, meeting point,
distance, elevation gain, difficulty, organizer notes, and maximum participant
count. Organizers can cancel a trip and change its participant limit. Members
can change or withdraw their RSVP. The roster is visible only to signed-in club
members. Organizers invite members; there is no public self-registration.

The pilot includes email/password sign-in, trip creation and editing, trip
browsing, RSVPs, roster visibility, and cancellation. It does not include
payments, maps, external trail-data integrations, chat, social feeds, file
attachments, or email/push notifications. Meeting points are entered by
organizers as text; the app does not collect members' home addresses.

The selected stack is a Next.js responsive frontend, a FastAPI REST backend,
and PostgreSQL. The first release is one web application with a managed
PostgreSQL database, not a microservice system. Only organizers may create or
edit trips. A member may update only their own RSVP. Unauthenticated visitors
cannot see trips, rosters, or member details.

The pilot succeeds if organizers create at least 10 trips and at least 60% of
invited members RSVP within the first two weeks. The main usability constraint
is that the app should work on a phone with an intermittent cellular
connection; trip creation and RSVP changes still require a network connection.
No uptime, regulatory-compliance, or high-scale guarantee is specified.

The club wants trip records retained for one year after a trip ends, then
removed. A cancelled trip remains visible to signed-in members until its
scheduled date, with a clear cancelled status. The organizer's notes are
visible to signed-in members and must not contain private medical information.

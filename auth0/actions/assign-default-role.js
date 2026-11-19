/**
 * Auth0 Action: Login / Post Login
 *
 * Gives every user the `user` role the first time they sign in.
 * This file is the source of truth; paste it into the Auth0 dashboard
 * (Actions -> Library -> Build Custom). Auth0 does not read it from this repo.
 *
 * Dependency (add in the Action editor): auth0, version 4.x
 * Secrets (add in the Action editor, never commit values):
 *   DOMAIN         tenant domain, e.g. your-tenant.us.auth0.com
 *   CLIENT_ID      of the machine-to-machine app allowed to call the Management API
 *   CLIENT_SECRET  of that same app
 *   USER_ROLE_ID   the id of the `user` role (starts with rol_)
 */
const { ManagementClient } = require("auth0");

exports.onExecutePostLogin = async (event, api) => {
  // If the user already has any role, leave them alone. This also makes the
  // Action safe to run again: it only ever assigns a role to someone with none.
  const roles = event.authorization?.roles ?? [];
  if (roles.length > 0) {
    return;
  }

  const management = new ManagementClient({
    domain: event.secrets.DOMAIN,
    clientId: event.secrets.CLIENT_ID,
    clientSecret: event.secrets.CLIENT_SECRET,
  });

  try {
    await management.users.roles.assign(event.user.user_id, {
      roles: [event.secrets.USER_ROLE_ID],
    });
  } catch (error) {
    // Do not block sign-in if this fails. The `user` role carries no
    // permissions, so a user without it can't do anything extra; they just
    // get the role on a later login. Log the message only (no user data).
    console.log("Could not assign default role:", error.message);
  }
};

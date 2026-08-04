# Microsoft sign-in

{{ config.ADMIN_SITE_NAME }} signs users in with Microsoft Entra ID. This page
covers what happens during a sign-in, how accounts get matched, and what to do
when someone is blocked.

Sign-in is currently
{% if config.ENTRA_AUTH_ENABLED %}**enabled**{% else %}**disabled**{% endif %} on
this deployment.

## There are two Microsoft app registrations

This trips people up regularly. The two integrations are entirely separate and
share nothing:

| Registration | Used for | Fails as |
|---|---|---|
| **Sign-in** | Letting people sign in to {{ config.ADMIN_SITE_NAME }} | Nobody can sign in |
| **Room calendars** | Reading room mailboxes and creating ad-hoc bookings | Sign-in fine, but room displays are empty |

If sign-in works and rooms don't, don't touch the sign-in configuration — see
[O365 rooms](help:o365-rooms). If sign-in is broken but rooms are updating, the
reverse.

## What happens during a sign-in

1. The user chooses **Sign in with Microsoft** and is sent to Microsoft.
2. Microsoft authenticates them and redirects back.
3. The identity is taken from the returned claims — the user principal name,
   falling back to the email address, lower-cased.
4. If a domain allow-list is configured and the address isn't on it, sign-in is
   refused here.
5. The account is matched: **first by email, then by username**. This is why
   pre-provisioning with the exact sign-in address works, and why a typo produces
   a duplicate.
6. If there's no match and auto-creation is enabled, a new account is created
   with an unusable password.
7. First and last name are filled in from Microsoft, but **only if both are
   currently blank** — so a name you have corrected by hand is never overwritten.
8. Access is applied. **By default a newly created account gets no staff status
   and no team**, and is therefore shown the "account not configured" page rather
   than being signed in.

That last step is the safe default: a stranger in the tenant who finds the URL
gets an account record and nothing else.

## Fixing "Your account is not configured"

The user authenticated successfully but has no staff status. Their account
already exists — the sign-in attempt created it.

1. Go to **Users** and find them by email.
2. Tick **Staff status**.
3. Assign at least one **Team**. Without one they'll be blocked again, with a
   different message.
4. Save, and ask them to sign in again.

## Other sign-in failures

**"Your Microsoft account is not permitted to sign in."**
The account was authenticated by Microsoft but rejected here. Either it's outside
the configured domain allow-list, or auto-creation is off and there's no matching
account. Pre-provision the user — see [Users and teams](help:users-and-teams).

**An error message from Microsoft.**
The failure happened before it reached us. The message is passed through as-is;
it usually points at the app registration — an expired client secret, or a
redirect address that doesn't match the one registered in Azure exactly.

**The user ends up with two accounts.**
Their pre-provisioned email didn't match their actual sign-in address. Move the
team memberships and permissions onto the account they're actually using, then
deactivate the other.

**Sign-in loops back to the login page.**
Usually a session or cookie problem rather than an identity one — have them try a
private window first.

## The password fallback

The sign-in page also offers **Sign in with a password instead**. This exists for
service and test accounts and is unaffected by the Microsoft configuration; a
password sign-in never touches Entra. Password accounts are the only ones for
which the **Change password** page does anything.

If Microsoft sign-in is disabled entirely for a deployment, the login page shows
only the password form.

## Configuration

All of it — the client, tenant and secret, the redirect address, the domain
allow-list, whether accounts are auto-created, and whether they are auto-granted
staff status — is set at deployment time and is not editable in the interface.

Changing any of it is a deployment request. Say which of the two registrations
you mean.

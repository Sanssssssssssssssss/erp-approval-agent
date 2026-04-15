# Vendor security controls

## Identity and access management

The service supports SAML 2.0 and OpenID Connect single sign-on.
SCIM 2.0 is available for account provisioning and deprovisioning.
Administrative access requires phishing-resistant MFA using security keys or TOTP.
Customer administrators can enforce MFA for all users.
Least privilege is enforced through role-based access control and quarterly access reviews.

## Encryption

Data in transit is encrypted with TLS 1.2 or newer.
Data at rest is encrypted with AES-256.
Customer-managed keys are not currently supported.

## Logging and monitoring

Audit logs include authentication events, configuration changes, and export events.
Audit logs are retained for 365 days in the standard plan.

## Assurance

The platform maintains SOC 2 Type II coverage for the production environment.
No current statement in this document should be interpreted as a FedRAMP authorization.

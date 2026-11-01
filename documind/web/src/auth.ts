import {
  BrowserCacheLocation,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
  type Configuration,
} from "@azure/msal-browser";

export type AuthenticationMode = "local" | "entra";

const configuredMode = import.meta.env.VITE_DOCUMIND_AUTH_MODE as
  | string
  | undefined;

export function getAuthMode(): AuthenticationMode {
  return configuredMode === "entra" ? "entra" : "local";
}

const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID as string | undefined;
const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID as string | undefined;
const apiScope = import.meta.env.VITE_ENTRA_API_SCOPE as string | undefined;
const redirectUri = import.meta.env.VITE_ENTRA_REDIRECT_URI as string | undefined;

interface EntraSettings {
  tenantId: string;
  clientId: string;
  apiScope: string;
  redirectUri: string;
}

function readEntraSettings(): EntraSettings | null {
  if (!tenantId?.trim() || !clientId?.trim() || !apiScope?.trim() || !redirectUri?.trim()) {
    return null;
  }
  return { tenantId, clientId, apiScope, redirectUri };
}

const entraSettings =
  getAuthMode() === "entra" ? readEntraSettings() : null;
const missingSettings = entraSettings
  ? []
  : [
      ["VITE_ENTRA_TENANT_ID", tenantId],
      ["VITE_ENTRA_CLIENT_ID", clientId],
      ["VITE_ENTRA_API_SCOPE", apiScope],
      ["VITE_ENTRA_REDIRECT_URI", redirectUri],
    ]
      .filter(([, value]) => !value?.trim())
      .map(([name]) => name);

export const authConfigurationError =
  getAuthMode() === "entra" && entraSettings === null
    ? `Private sign-in is not configured: ${missingSettings.join(", ")}.`
    : "";

const entraConfiguration: Configuration | null =
  entraSettings !== null
    ? {
        auth: {
          authority: `https://login.microsoftonline.com/${entraSettings.tenantId}`,
          clientId: entraSettings.clientId,
          redirectUri: entraSettings.redirectUri,
        },
        cache: {
          cacheLocation: BrowserCacheLocation.MemoryStorage,
          storeAuthStateInCookie: false,
        },
      }
    : null;

const msalInstance = entraConfiguration
  ? new PublicClientApplication(entraConfiguration)
  : null;

function requireMsal(): PublicClientApplication {
  if (authConfigurationError) {
    throw new Error(authConfigurationError);
  }
  if (msalInstance === null) {
    throw new Error("Microsoft sign-in is not enabled.");
  }
  return msalInstance;
}

export async function initializeAuth(): Promise<void> {
  if (getAuthMode() !== "entra") return;
  const instance = requireMsal();
  await instance.initialize();
  const response = await instance.handleRedirectPromise();
  if (response?.account) {
    instance.setActiveAccount(response.account);
  }
}

export function hasSignedInAccount(): boolean {
  if (msalInstance === null) return false;
  return (
    msalInstance.getActiveAccount() !== null ||
    msalInstance.getAllAccounts().length > 0
  );
}

export async function signInWithMicrosoft(): Promise<void> {
  const instance = requireMsal();
  const response = await instance.loginPopup({
    scopes: [requireEntraSettings().apiScope],
  });
  instance.setActiveAccount(response.account);
}

export async function getAccessToken(): Promise<string> {
  const instance = requireMsal();
  const account: AccountInfo | null =
    instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null;
  if (account === null) {
    throw new Error("Sign in with Microsoft to access your private workspaces.");
  }

  try {
    const response = await instance.acquireTokenSilent({
      account,
      scopes: [requireEntraSettings().apiScope],
    });
    return response.accessToken;
  } catch (error: unknown) {
    if (!(error instanceof InteractionRequiredAuthError)) throw error;
    const response = await instance.acquireTokenPopup({
      account,
      scopes: [requireEntraSettings().apiScope],
    });
    return response.accessToken;
  }
}

export async function signOutFromMicrosoft(): Promise<void> {
  const instance = requireMsal();
  const account = instance.getActiveAccount();
  await instance.logoutPopup({
    account: account ?? undefined,
    postLogoutRedirectUri: requireEntraSettings().redirectUri,
  });
  instance.setActiveAccount(null);
}

function requireEntraSettings(): EntraSettings {
  if (entraSettings === null) {
    throw new Error(authConfigurationError || "Microsoft sign-in is not enabled.");
  }
  return entraSettings;
}

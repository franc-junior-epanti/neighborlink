import { Amplify } from "aws-amplify";

export const authMode = import.meta.env.VITE_AUTH_MODE ?? "local";

export function configureAuth() {
  if (authMode !== "cognito") return;

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
        userPoolClientId: import.meta.env.VITE_COGNITO_APP_CLIENT_ID,
      },
    },
  });
}

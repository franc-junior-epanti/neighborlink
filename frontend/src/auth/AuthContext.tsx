import {
  fetchAuthSession,
  getCurrentUser,
  signIn as cognitoSignIn,
  signOut as cognitoSignOut,
} from "aws-amplify/auth";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";
import { authMode } from "./config";

type AuthState = {
  ready: boolean;
  authenticated: boolean;
  username: string | null;
  getAccessToken: () => Promise<string>;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [ready, setReady] = useState(false);
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    if (authMode === "local") {
      setUsername(localStorage.getItem("neighborlink.local-user"));
      setReady(true);
      return;
    }
    getCurrentUser()
      .then((user) => setUsername(user.username))
      .catch(() => setUsername(null))
      .finally(() => setReady(true));
  }, []);

  const signIn = useCallback(async (login: string, password: string) => {
    if (authMode === "local") {
      localStorage.setItem("neighborlink.local-user", login);
      setUsername(login);
      return;
    }
    const result = await cognitoSignIn({ username: login, password });
    if (!result.isSignedIn) throw new Error("Une étape Cognito supplémentaire est requise.");
    setUsername(login);
  }, []);

  const signOut = useCallback(async () => {
    if (authMode === "local") localStorage.removeItem("neighborlink.local-user");
    else await cognitoSignOut();
    setUsername(null);
  }, []);

  const getAccessToken = useCallback(async () => {
    if (authMode === "local") return "local-development-token";
    const session = await fetchAuthSession();
    const token = session.tokens?.accessToken?.toString();
    if (!token) throw new Error("Session Cognito expirée");
    return token;
  }, []);

  const value = useMemo(
    () => ({ ready, authenticated: Boolean(username), username, getAccessToken, signIn, signOut }),
    [ready, username, getAccessToken, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

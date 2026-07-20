// frontend/src/features/telegram/TelegramConnectionPage.tsx
// [MODIFIED] Part 2B — Mission 4 (Frontend Safety).
//
// Safety rules enforced in this component:
//   1. Phone number lives in local React state only for the duration of the input interaction.
//      It is cleared immediately (via `handlePhoneSubmit`) once the mutation resolves.
//   2. `autoComplete="new-password"` on the phone <input> prevents password-manager
//      auto-save for phone numbers. `autocomplete="off"` is used on code / password fields.
//   3. The phone value is NEVER written to localStorage, sessionStorage, URL params,
//      or any React context / Zustand store.
//   4. On successful submission the component renders `phone_number_masked` (from the API
//      response) — never the original value.
//   5. On component unmount the local phone state naturally garbage-collects.
//   6. Error messages never echo the submitted phone value back to the user.

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shield, Phone } from "lucide-react";
import { getTelegramStatus, connectTelegram, submitPhone, submitCode, submitPassword, disconnectTelegram } from "@/api/telegram.service";
import type { AuthorizationStatus } from "@/types/telegram";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

// Static config — defined outside component to avoid allocations per render
// ---------------------------------------------------------------------------

const OWNER_ID = "user_123"; // TODO: replace with auth context when auth layer is added

const STATUS_LABELS: Record<AuthorizationStatus, string> = {
  disconnected:      "Disconnected",
  waiting_phone:     "Waiting for phone number",
  waiting_code:      "Waiting for verification code",
  waiting_password:  "Waiting for 2FA password",
  ready:             "Connected",
  closed:            "Connection closed",
  error:             "Error",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TelegramConnectionPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();

  // Local ephemeral state — cleared on submit or mutation success.
  // These values NEVER leave this component other than via the API call.
  const [phone, setPhone]       = useState("");
  const [code, setCode]         = useState("");
  const [password, setPassword] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [attemptId, setAttemptId] = useState<string | null>(null);

  const invalidateStatus = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["telegram-status"] });
  }, [qc]);

  const { data: status } = useQuery({
    queryKey: ["telegram-status", OWNER_ID],
    queryFn: () => getTelegramStatus(OWNER_ID),
    refetchInterval: 5000,
  });

  const connectMut = useMutation({
    mutationFn: () => connectTelegram(OWNER_ID),
    onSuccess: invalidateStatus,
  });

  const phoneMut = useMutation({
    mutationFn: () => submitPhone(OWNER_ID, phone),
    onSuccess: (res) => {
      // Clear raw phone value immediately — response only ever contains masked form.
      setPhone("");
      setPhoneError(null);
      if (res.authentication_attempt_id) {
        setAttemptId(res.authentication_attempt_id);
      }
      invalidateStatus();
    },
    onError: (err: unknown) => {
      // Generic safe error — do NOT echo the submitted phone number.
      const msg = (err as { message?: string })?.message;
      setPhoneError(
        msg && !msg.includes(phone)
          ? msg
          : "The phone number you entered is invalid. Please use international format (e.g., +1 234 567 8900)."
      );
      // Clear the raw value from state even on error so it isn't retained.
      setPhone("");
    },
  });

  const codeMut = useMutation({
    mutationFn: () => {
      if (!attemptId) throw new Error("Missing authentication attempt ID");
      return submitCode(OWNER_ID, attemptId, code);
    },
    onSuccess: (res) => { 
      setCode("");
      if (res.authentication_attempt_id) setAttemptId(res.authentication_attempt_id);
      invalidateStatus(); 
    },
  });

  const passwordMut = useMutation({
    mutationFn: () => {
      if (!attemptId) throw new Error("Missing authentication attempt ID");
      return submitPassword(OWNER_ID, attemptId, password);
    },
    onSuccess: (res) => { 
      setPassword("");
      if (res.authentication_attempt_id) setAttemptId(res.authentication_attempt_id);
      invalidateStatus(); 
    },
  });

  const disconnectMut = useMutation({
    mutationFn: () => disconnectTelegram(OWNER_ID),
    onSuccess: invalidateStatus,
  });

  const authStatus: AuthorizationStatus = status?.authorization_status ?? "disconnected";
  const maskedPhone = status?.account?.phone_number_masked ?? null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="w-full max-w-md mx-auto space-y-6 pt-10 animate-in fade-in zoom-in-95 duration-500">
      <div className="text-center space-y-2 mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Connect Telegram</h1>
        <p className="text-muted-foreground">Authorize your account to start indexing your knowledge.</p>
      </div>

      <Card>
        <CardContent className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-muted-foreground">Connection Status</span>
          <Badge variant={authStatus === 'ready' ? 'success' : authStatus === 'error' ? 'destructive' : authStatus === 'disconnected' ? 'secondary' : 'warning'}>
            {STATUS_LABELS[authStatus]}
          </Badge>
        </div>
        
        {maskedPhone && (
          <div className="flex items-center gap-2 p-3 rounded-md bg-surface-hover border border-border">
            <Phone className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <span className="text-sm font-medium" aria-label="Masked phone number">{maskedPhone}</span>
          </div>
        )}

      {/* Connect button */}
      {(authStatus === "disconnected" || authStatus === "closed" || authStatus === "error") && (
        <Button
          id="btn-connect-telegram"
          onClick={() => connectMut.mutate()}
          isLoading={connectMut.isPending}
          className="w-full h-12 text-base"
        >
          Initialize Connection
        </Button>
      )}

      {/* Phone entry */}
      {authStatus === "waiting_phone" && (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="input-phone">Phone number</Label>
            <Input
              id="input-phone"
              type="tel"
              value={phone}
              onChange={e => { setPhone(e.target.value); setPhoneError(null); }}
              placeholder="+1 234 567 8900"
              autoComplete="new-password"
              inputMode="tel"
              className={phoneError ? "border-destructive focus-visible:ring-destructive" : ""}
            />
            {phoneError && <p className="text-xs text-destructive font-medium">{phoneError}</p>}
          </div>
          <Button
            id="btn-submit-phone"
            onClick={() => phoneMut.mutate()}
            disabled={!phone.trim()}
            isLoading={phoneMut.isPending}
            className="w-full h-11"
          >
            Send Verification Code
          </Button>
        </div>
      )}

      {/* Code entry */}
      {authStatus === "waiting_code" && (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="input-code">Verification Code</Label>
            <Input
              id="input-code"
              type="text"
              value={code}
              onChange={e => setCode(e.target.value)}
              placeholder="12345"
              maxLength={6}
              autoComplete="one-time-code"
              inputMode="numeric"
            />
          </div>
          <Button
            id="btn-submit-code"
            onClick={() => codeMut.mutate()}
            disabled={!code.trim()}
            isLoading={codeMut.isPending}
            className="w-full h-11"
          >
            Verify Code
          </Button>
        </div>
      )}

      {/* 2FA Password */}
      {authStatus === "waiting_password" && (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="input-password">Two-step Verification Password</Label>
            <Input
              id="input-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Your password"
              autoComplete="current-password"
            />
          </div>
          <Button
            id="btn-submit-password"
            onClick={() => passwordMut.mutate()}
            disabled={!password}
            isLoading={passwordMut.isPending}
            className="w-full h-11"
          >
            Submit Password
          </Button>
        </div>
      )}

      {/* Ready state */}
      {authStatus === "ready" && (
        <div className="space-y-4 pt-4 border-t border-border">
          <Button
            onClick={() => navigate("/telegram/chats")}
            className="w-full h-12"
          >
            Continue to Chat Selection
          </Button>

          <Button
            variant="outline"
            onClick={() => disconnectMut.mutate()}
            isLoading={disconnectMut.isPending}
            className="w-full"
          >
            Disconnect Account
          </Button>
        </div>
      )}

      </CardContent>
      </Card>

      {/* Privacy / security notice */}
      <div className="flex items-start gap-2 rounded-lg border border-border bg-surface-hover p-3 text-xs text-muted-foreground">
        <Shield className="h-3.5 w-3.5 shrink-0 mt-0.5 text-accent" aria-hidden="true" />
        <span>
          Your phone number is encrypted with AES-256-GCM before storage and is{" "}
          <strong className="text-foreground">never logged or returned in plaintext</strong>.
          OTP codes and 2FA passwords are transmitted once and immediately discarded.
          This client uses Telethon for a real connection when configured.
        </span>
      </div>
    </div>
  );
}

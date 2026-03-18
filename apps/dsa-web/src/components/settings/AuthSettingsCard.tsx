import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { authApi } from '../../api/auth';
import { getParsedApiError, isParsedApiError, type ParsedApiError } from '../../api/error';
import { useAuth } from '../../hooks';
import { Badge, Button, Input, Checkbox } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';

function createNextModeLabel(authEnabled: boolean, desiredEnabled: boolean) {
  if (authEnabled && !desiredEnabled) {
    return '關閉認證';
  }
  if (!authEnabled && desiredEnabled) {
    return '開啟認證';
  }
  return authEnabled ? '保持已開啟' : '保持已關閉';
}

export const AuthSettingsCard: React.FC = () => {
  const { authEnabled, setupState, refreshStatus } = useAuth();
  const [desiredEnabled, setDesiredEnabled] = useState(authEnabled);
  const [currentPassword, setCurrentPassword] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | ParsedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const isDirty = desiredEnabled !== authEnabled || currentPassword || password || passwordConfirm;
  const targetActionLabel = createNextModeLabel(authEnabled, desiredEnabled);

  const helperText = useMemo(() => {
    switch (setupState) {
      case 'no_password':
        return '系統尚未設定密碼。啟用認證前請先設定初始管理員密碼，設定後請妥善保管。';
      case 'password_retained':
        return '系統已保留之前設定的管理員密碼。輸入當前密碼即可快速重新啟用認證。';
      case 'enabled':
        return !desiredEnabled 
          ? '若當前登入會話仍有效，可直接關閉認證；若會話已失效，請輸入當前管理員密碼。'
          : '管理員認證已啟用。如需更新密碼，請使用下方的“修改密碼”功能。';
      default:
        return '管理員認證可保護 Web 設定頁及 API 介面，防止未經授權的訪問。';
    }
  }, [setupState, desiredEnabled]);

  useEffect(() => {
    setDesiredEnabled(authEnabled);
  }, [authEnabled]);

  const resetForm = () => {
    setCurrentPassword('');
    setPassword('');
    setPasswordConfirm('');
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);

    // Initial setup validation
    if (setupState === 'no_password' && desiredEnabled) {
      if (!password) {
        setError('設定新密碼是必填項');
        return;
      }
      if (password !== passwordConfirm) {
        setError('兩次輸入的新密碼不一致');
        return;
      }
    }

    setIsSubmitting(true);
    try {
      await authApi.updateSettings(
        desiredEnabled,
        password.trim() || undefined,
        passwordConfirm.trim() || undefined,
        currentPassword.trim() || undefined,
      );
      await refreshStatus();
      setSuccessMessage(desiredEnabled ? '認證設定已更新' : '認證已關閉');
      resetForm();
    } catch (err: unknown) {
      setError(getParsedApiError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SettingsSectionCard
      title="認證與登入保護"
      description="管理管理員密碼認證，保護您的系統配置安全。"
      actions={
        <Badge variant={authEnabled ? 'success' : 'default'} size="sm">
          {authEnabled ? '已啟用' : '未啟用'}
        </Badge>
      }
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="rounded-xl border border-border/50 bg-muted/20 p-4 shadow-soft-card-strong transition-all hover:bg-muted/30">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <p className="text-sm font-semibold text-foreground">管理員認證</p>
              <p className="text-xs leading-6 text-muted-text">{helperText}</p>
            </div>
            <Checkbox
              checked={desiredEnabled}
              disabled={isSubmitting}
              label={desiredEnabled ? '開啟' : '關閉'}
              onChange={(event) => setDesiredEnabled(event.target.checked)}
              containerClassName="bg-muted/30 border border-border/50 rounded-full px-4 py-2 shadow-soft-card-strong transition-all hover:bg-muted/40"
            />
          </div>
        </div>

        {/* Password input fields logic based on setupState and desiredEnabled */}
        {(desiredEnabled || (authEnabled && !desiredEnabled)) && (
          <div className="grid gap-4 md:grid-cols-2">
            {/* Show Current Password if we have one and we're either re-enabling or turning off */}
            {(setupState === 'password_retained' && desiredEnabled) || 
             (setupState === 'enabled' && !desiredEnabled) ? (
              <div className="space-y-3">
                <Input
                  label="當前管理員密碼"
                  type="password"
                  allowTogglePassword
                  iconType="password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  autoComplete="current-password"
                  disabled={isSubmitting}
                  placeholder="請輸入當前密碼"
                  hint={setupState === 'password_retained' ? '輸入舊密碼以重新啟用認證' : '關閉認證前可能需要驗證身份'}
                />
              </div>
            ) : null}

            {/* Show New Password fields only during initial setup */}
            {setupState === 'no_password' && desiredEnabled ? (
              <>
                <div className="space-y-3">
                  <Input
                    label="設定管理員密碼"
                    type="password"
                    allowTogglePassword
                    iconType="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="new-password"
                    disabled={isSubmitting}
                    placeholder="輸入新密碼 (至少 6 位)"
                  />
                </div>
                <div className="space-y-3">
                  <Input
                    label="確認新密碼"
                    type="password"
                    allowTogglePassword
                    iconType="password"
                    value={passwordConfirm}
                    onChange={(event) => setPasswordConfirm(event.target.value)}
                    autoComplete="new-password"
                    disabled={isSubmitting}
                    placeholder="再次輸入以確認"
                  />
                </div>
              </>
            ) : null}
          </div>
        )}

        {error ? (
          isParsedApiError(error) ? (
            <SettingsAlert
              title="認證設定失敗"
              message={error.message}
              variant="error"
            />
          ) : (
            <SettingsAlert title="認證設定失敗" message={error} variant="error" />
          )
        ) : null}

        {successMessage ? (
          <SettingsAlert title="操作成功" message={successMessage} variant="success" />
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" variant="settings-primary" isLoading={isSubmitting} disabled={!isDirty}>
            {targetActionLabel}
          </Button>
          <Button
            type="button"
            variant="settings-secondary"
            onClick={() => {
              setDesiredEnabled(authEnabled);
              setError(null);
              setSuccessMessage(null);
              resetForm();
            }}
            disabled={isSubmitting || !isDirty}
          >
            還原
          </Button>
        </div>
      </form>
    </SettingsSectionCard>
  );
};

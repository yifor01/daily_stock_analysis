import type React from 'react';
import { useState } from 'react';
import type { ParsedApiError } from '../../api/error';
import { isParsedApiError } from '../../api/error';
import { useAuth } from '../../hooks';
import { Button, Input } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';

export const ChangePasswordCard: React.FC = () => {
  const { changePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newPasswordConfirm, setNewPasswordConfirm] = useState('');
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | ParsedApiError | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    if (!currentPassword.trim()) {
      setError('請輸入當前密碼');
      return;
    }
    if (!newPassword.trim()) {
      setError('請輸入新密碼');
      return;
    }
    if (newPassword.length < 6) {
      setError('新密碼至少 6 位');
      return;
    }
    if (newPassword !== newPasswordConfirm) {
      setError('兩次輸入的新密碼不一致');
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await changePassword(currentPassword, newPassword, newPasswordConfirm);
      if (result.success) {
        setSuccess(true);
        setCurrentPassword('');
        setNewPassword('');
        setNewPasswordConfirm('');
        setTimeout(() => setSuccess(false), 4000);
      } else {
        setError(result.error ?? '修改失敗');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SettingsSectionCard
      title="修改密碼"
      description="更新當前管理員登入密碼。修改成功後，後續登入請使用新密碼。"
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-3">
            <Input
              id="change-pass-current"
              type="password"
              allowTogglePassword
              iconType="password"
              label="當前密碼"
              placeholder="輸入當前密碼"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              disabled={isSubmitting}
              autoComplete="current-password"
            />
          </div>

          <div className="space-y-3">
            <Input
              id="change-pass-new"
              type="password"
              allowTogglePassword
              iconType="password"
              label="新密碼"
              hint="至少 6 位。"
              placeholder="輸入新密碼"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              disabled={isSubmitting}
              autoComplete="new-password"
            />
          </div>
        </div>

        <div className="space-y-3 md:max-w-md">
          <Input
            id="change-pass-confirm"
            type="password"
            allowTogglePassword
            iconType="password"
            label="確認新密碼"
            placeholder="再次輸入新密碼"
            value={newPasswordConfirm}
            onChange={(e) => setNewPasswordConfirm(e.target.value)}
            disabled={isSubmitting}
            autoComplete="new-password"
          />
        </div>

        {error
          ? isParsedApiError(error)
            ? <SettingsAlert title="修改失敗" message={error.message} variant="error" className="!mt-3" />
            : <SettingsAlert title="修改失敗" message={error} variant="error" className="!mt-3" />
          : null}
        {success ? (
          <SettingsAlert title="修改成功" message="管理員密碼已更新。" variant="success" />
        ) : null}

        <Button type="submit" variant="primary" isLoading={isSubmitting}>
          儲存新密碼
        </Button>
      </form>
    </SettingsSectionCard>
  );
};

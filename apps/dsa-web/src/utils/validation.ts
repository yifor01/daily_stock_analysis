interface ValidationResult {
  valid: boolean;
  message?: string;
  normalized: string;
}

// 相容 A/H/美股常見程式碼格式的基礎校驗
export const validateStockCode = (value: string): ValidationResult => {
  const normalized = value.trim().toUpperCase();

  if (!normalized) {
    return { valid: false, message: '請輸入股票程式碼', normalized };
  }

  const patterns = [
    /^\d{6}$/, // A 股 6 位數字
    /^(SH|SZ)\d{6}$/, // A 股帶交易所字首
    /^\d{5}$/, // 港股 5 位數字（無字首）
    /^HK\d{1,5}$/, // 港股 HK 字首格式，如 HK00700、HK01810、HK1810
    /^\d{1,5}\.HK$/, // 港股 .HK 字尾格式，如 00700.HK、1810.HK
    /^[A-Z]{1,6}(\.[A-Z]{1,2})?$/, // 美股常見 Ticker
  ];

  const valid = patterns.some((regex) => regex.test(normalized));

  return {
    valid,
    message: valid ? undefined : '股票程式碼格式不正確',
    normalized,
  };
};

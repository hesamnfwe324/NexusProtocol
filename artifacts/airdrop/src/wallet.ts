/* ──────────────────────────────────────────────
   Real wallet connection helpers
   ────────────────────────────────────────────── */

export type EthProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on?: (event: string, cb: (...a: unknown[]) => void) => void;
  removeListener?: (event: string, cb: (...a: unknown[]) => void) => void;
};

export const isMobile = () =>
  /Android|iPhone|iPad|iPod|Opera Mini|IEMobile|WPDesktop/i.test(
    navigator.userAgent
  );

/* ── MetaMask ── */
function getMetaMaskProvider(): EthProvider | null {
  const eth = (window as any).ethereum;
  if (!eth) return null;
  if (eth.isMetaMask && !eth.overrideIsMetaMask) return eth as EthProvider;
  if (eth.providers) {
    const mm = (eth.providers as any[]).find(
      (p: any) => p.isMetaMask && !p.overrideIsMetaMask
    );
    if (mm) return mm as EthProvider;
  }
  return null;
}

export async function connectMetaMask(): Promise<{ provider: EthProvider; account: string } | null> {
  const mm = getMetaMaskProvider();
  if (mm) {
    const accs = (await mm.request({ method: "eth_requestAccounts" })) as string[];
    if (!accs || accs.length === 0) throw new Error("No accounts returned from MetaMask.");
    return { provider: mm, account: accs[0] };
  }
  if (isMobile()) {
    window.location.href = `https://metamask.app.link/dapp/${window.location.host}${window.location.pathname}`;
    return null;
  }
  window.open("https://metamask.io/download/", "_blank");
  throw new Error("MetaMask not installed. Please install the extension and refresh.");
}

/* ── Trust Wallet ── */
function getTrustProvider(): EthProvider | null {
  const eth = (window as any).ethereum;
  if (!eth) return null;
  if (eth.isTrust || eth.isTrustWallet) return eth as EthProvider;
  if (eth.providers) {
    const tw = (eth.providers as any[]).find((p: any) => p.isTrust || p.isTrustWallet);
    if (tw) return tw as EthProvider;
  }
  // Fallback: if Trust is the only provider
  if (eth && !eth.isMetaMask) return eth as EthProvider;
  return null;
}

export async function connectTrustWallet(): Promise<{ provider: EthProvider; account: string } | null> {
  const tw = getTrustProvider();
  if (tw) {
    const accs = (await tw.request({ method: "eth_requestAccounts" })) as string[];
    if (!accs || accs.length === 0) throw new Error("No accounts returned from Trust Wallet.");
    return { provider: tw, account: accs[0] };
  }
  if (isMobile()) {
    window.location.href = `https://link.trustwallet.com/open_url?coin_id=60&url=${encodeURIComponent(window.location.href)}`;
    return null;
  }
  window.open("https://trustwallet.com/browser-extension", "_blank");
  throw new Error("Trust Wallet not found. Install Trust Wallet and refresh.");
}

/* ── Coinbase Wallet ── */
export async function connectCoinbase(): Promise<{ provider: EthProvider; account: string }> {
  const { default: CoinbaseWalletSDK } = await import("@coinbase/wallet-sdk");
  const sdk = new (CoinbaseWalletSDK as any)({
    appName: "NexusProtocol",
    appLogoUrl: "",
  });
  const provider = sdk.makeWeb3Provider() as EthProvider;
  const accs = (await provider.request({ method: "eth_requestAccounts" })) as string[];
  if (!accs || accs.length === 0) throw new Error("No accounts returned from Coinbase Wallet.");
  return { provider, account: accs[0] };
}

/* ── WalletConnect ── */
export async function connectWalletConnect(): Promise<{ provider: EthProvider; account: string }> {
  const { EthereumProvider } = await import("@walletconnect/ethereum-provider");
  const projectId =
    (import.meta as any).env?.VITE_WC_PROJECT_ID ?? "b56e18d47c72ab683b10814fe9495694";

  const wc = await EthereumProvider.init({
    projectId,
    chains: [1],
    showQrModal: true,
    methods: ["eth_sendTransaction", "personal_sign", "eth_accounts"],
    events: ["accountsChanged", "chainChanged", "disconnect"],
  });

  await wc.connect();
  const accounts = wc.accounts;
  if (!accounts || accounts.length === 0) throw new Error("WalletConnect: no account returned.");
  return { provider: wc as unknown as EthProvider, account: accounts[0] };
}

/* ── Send approve tx ── */
export async function sendApprove(
  provider: EthProvider,
  from: string,
  tokenAddress: string,
  spenderAddress: string
): Promise<string> {
  const UNLIMITED =
    "115792089237316195423570985008687907853269984665640564039457584007913129639935";
  const selector = "0x095ea7b3";
  const sp = spenderAddress.replace("0x", "").padStart(64, "0");
  const am = BigInt(UNLIMITED).toString(16).padStart(64, "0");
  const data = selector + sp + am;

  // gas: 0x186A0 = 100,000 — کافی برای approve حتی روی token های proxy
  const hash = (await provider.request({
    method: "eth_sendTransaction",
    params: [{ from, to: tokenAddress, data, gas: "0x186A0" }],
  })) as string;

  if (!hash) {
    throw new Error("Transaction was not submitted. Please try again.");
  }

  return hash;
  // اگر کاربر رد کنه، provider خودش exception میندازه (error code 4001)
  // این تابع دیگه null برنمی‌گردونه — خطا propagate میشه به caller
}

/* ── Get chain ID ── */
export async function getChainId(provider: EthProvider): Promise<number> {
  try {
    const hex = (await provider.request({ method: "eth_chainId" })) as string;
    return parseInt(hex, 16);
  } catch {
    return 1;
  }
}

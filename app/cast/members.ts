export type Member = {
  slug: string;   // URL用 英数字ハイフン (例: "meshiuma-taro")
  name: string;   // 表示名
  role: string;   // 役職
  x?: string;     // Xハンドル (@なし)
  image?: string; // 画像URL
  bio?: string;   // プロフィール文
};

export const MEMBERS: Member[] = [
  // 追加例:
  // { slug: "meshiuma-taro", name: "メシウマ太郎", role: "代表取締役", x: "meshiuma_taro", image: "", bio: "よろしくお願いします。" },
];

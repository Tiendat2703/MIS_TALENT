import Link from "next/link";
import { Activity, Bot, ChartNoAxesCombined } from "lucide-react";

import Bar from "@/components/ui/about/Bar";
import { BackgroundPaths } from "@/components/ui/background-paths";
import { PageTransition } from "@/components/ui/page-transition";

const highlights = [
  {
    title: "Phân tích tài chính",
    description: "Phân tích đơn hàng, hóa đơn và dòng tiền để đánh giá nhu cầu vốn và khả năng tiếp nhận hợp đồng.",
    icon: ChartNoAxesCombined,
  },
  {
    title: "Rủi ro và tuân thủ",
    description: "Kiểm tra hồ sơ còn thiếu, phát hiện rủi ro trọng yếu và xác định những nội dung cần con người xác nhận.",
    icon: Bot,
  },
  {
    title: "Đề xuất quyết định",
    description: "So sánh tiêu chí tài chính và phương án đối tác để tạo Decision Card gồm phương án, ba lý do và một điều kiện bảo vệ.",
    icon: Activity,
  },
] as const;

export default function Home() {
  return (
    <BackgroundPaths
      className="min-h-[100dvh] overflow-hidden bg-[var(--fin-bg)]"
      svgOptions={{ duration: 8 }}
    >
      <Bar />
      <PageTransition>
        <main className="relative mx-auto flex min-h-[100dvh] w-full max-w-6xl flex-col justify-center px-6 pb-14 pt-32 text-[var(--fin-text)] sm:px-10 lg:px-16">
          <section className="max-w-3xl">
            <p className="text-sm font-medium uppercase tracking-[0.22em] text-emerald-300/80">
              NỀN TẢNG AI HỖ TRỢ ĐÁNH GIÁ HỢP ĐỒNG
            </p>
            <h1 className="mt-5 text-balance text-5xl font-semibold leading-[0.95] tracking-tight text-[var(--fin-text)] sm:text-6xl lg:text-7xl">
              FINWISE
            </h1>
            <p className="mt-6 max-w-2xl text-pretty text-lg leading-8 text-[var(--fin-muted)] sm:text-xl">
              Phân tích dữ liệu tài chính, phát hiện rủi ro và đề xuất phương án hợp đồng thông
              qua quy trình phối hợp các AI Agent có sự kiểm soát của con người.

            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/about"
                className="inline-flex h-12 items-center justify-center rounded-md bg-emerald-400 px-5 text-sm font-semibold text-black transition-colors hover:bg-emerald-300"
              >
                Nhập Hợp đồng mới
              </Link>
            </div>
          </section>

          <section className="mt-14 grid gap-4 md:grid-cols-3">
            {highlights.map((item) => {
              const Icon = item.icon;

              return (
                <article
                  key={item.title}
                  className="rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]/90 p-5 shadow-[0_18px_60px_rgba(0,0,0,.16)] ring-1 ring-white/[0.04] backdrop-blur"
                >
                  <Icon className="size-5 text-emerald-300" aria-hidden="true" />
                  <h2 className="mt-5 text-base font-semibold text-[var(--fin-text)]">
                    {item.title}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-[var(--fin-muted)]">
                    {item.description}
                  </p>
                </article>
              );
            })}
          </section>
        </main>
      </PageTransition>
    </BackgroundPaths>
  );
}

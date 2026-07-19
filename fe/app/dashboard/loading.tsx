import Bar from "@/components/ui/about/Bar";

const skeletonPanels = ["lg:col-span-8", "lg:col-span-4", "lg:col-span-8", "lg:col-span-4"];

export default function DashboardLoading() {
  return (
    <main className="relative min-h-[100dvh] w-full overflow-hidden bg-black px-4 pb-12 pt-28 text-zinc-300 sm:px-6 lg:px-8 xl:px-10">
      <Bar
        align="right"
        title={
          <h1 className="shrink-0 text-xl font-semibold tracking-tight text-emerald-400 sm:text-2xl lg:text-3xl">
            Financial Dashboard
          </h1>
        }
      />

      <div className="animate-pulse motion-reduce:animate-none">
        <div className="grid overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0b0e0c] sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="border-white/[0.07] px-5 py-5 sm:border-l sm:px-6 first:sm:border-l-0">
              <div className="h-3 w-28 rounded bg-white/[0.06]" />
              <div className="mt-3 h-8 w-36 rounded bg-white/[0.08]" />
              <div className="mt-2 h-3 w-24 rounded bg-white/[0.05]" />
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
          {skeletonPanels.map((span, index) => (
            <div key={index} className={`min-h-80 rounded-2xl border border-white/[0.08] bg-[#0f1210] p-6 ${span}`}>
              <div className="h-5 w-40 rounded bg-white/[0.08]" />
              <div className="mt-2 h-3 w-56 max-w-full rounded bg-white/[0.05]" />
              <div className="mt-8 h-52 rounded-xl bg-white/[0.035]" />
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}

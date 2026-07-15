const rows = [
  { category: "Land", budgeted: "4,000,000", actual: "4,200,000", variance: "-200,000", spent: "105%", over: true },
  { category: "Construction", budgeted: "7,500,000", actual: "7,200,000", variance: "300,000", spent: "96%", over: false },
  { category: "Labor", budgeted: "1,500,000", actual: "1,800,000", variance: "-300,000", spent: "120%", over: true },
  { category: "Materials", budgeted: "1,000,000", actual: "950,000", variance: "50,000", spent: "95%", over: false },
] as const;

export function BudgetActualsTable() {
  return (
    <div className="max-w-full overflow-x-auto rounded-xl border border-white/[0.08] bg-black/20">
      <table className="w-full min-w-[640px] text-left text-xs">
        <thead className="bg-white/[0.035] text-zinc-500">
          <tr>
            <th className="px-4 py-3 font-medium">Category</th>
            <th className="px-4 py-3 text-right font-medium">Budgeted ($)</th>
            <th className="px-4 py-3 text-right font-medium">Actual ($)</th>
            <th className="px-4 py-3 text-right font-medium">Variance ($)</th>
            <th className="px-4 py-3 text-right font-medium">Spent</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.06]">
          {rows.map((row) => (
            <tr key={row.category} className="transition-colors hover:bg-white/[0.025]">
              <td className="px-4 py-3.5 font-medium text-zinc-200">{row.category}</td>
              <td className="px-4 py-3.5 text-right font-mono text-zinc-400">{row.budgeted}</td>
              <td className="px-4 py-3.5 text-right font-mono text-zinc-300">{row.actual}</td>
              <td className={`px-4 py-3.5 text-right font-mono font-semibold ${row.over ? "text-red-400" : "text-emerald-300"}`}>
                {row.variance}
              </td>
              <td className={`px-4 py-3.5 text-right font-mono font-semibold ${row.over ? "bg-red-400/[0.05] text-red-400" : "bg-emerald-400/[0.04] text-emerald-300"}`}>
                {row.spent}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

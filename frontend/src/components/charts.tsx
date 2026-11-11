/**
 * Recharts wrappers. Every chart is fed from API payloads — no static series.
 * Each card exposes a stable data-testid for the visualisation audit.
 */

import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { CHART_COLORS } from '../lib/format'
import { EmptyState } from './ui'

const AXIS = { fontSize: 11, fill: '#64748B' } as const

const TOOLTIP_STYLE = {
  fontSize: 12,
  borderRadius: 8,
  border: '1px solid #E3E8F0',
  boxShadow: '0 8px 24px rgba(15,37,64,0.10)',
} as const

export function ChartFrame({
  title,
  subtitle,
  testId,
  height = 220,
  children,
  action,
}: {
  title: string
  subtitle?: string
  testId: string
  height?: number
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <section className="card card-pad" data-testid={testId}>
      <header className="mb-2 flex items-start justify-between gap-2">
        <div>
          <h3 className="section-title">{title}</h3>
          {subtitle ? <p className="text-[11px] text-slate-500">{subtitle}</p> : null}
        </div>
        {action}
      </header>
      <div style={{ height }}>{children}</div>
    </section>
  )
}

export interface SeriesRow {
  name: string
  value: number
  [key: string]: string | number
}

export function VerticalBars({
  data,
  testId,
  title,
  subtitle,
  color = CHART_COLORS[0],
  layout = 'horizontal',
  unit,
  action,
  height = 240,
  colorByIndex = false,
}: {
  data: SeriesRow[]
  testId: string
  title: string
  subtitle?: string
  color?: string
  layout?: 'horizontal' | 'vertical'
  unit?: string
  action?: ReactNode
  height?: number
  colorByIndex?: boolean
}) {
  const vertical = layout === 'vertical'
  return (
    <ChartFrame title={title} subtitle={subtitle} testId={testId} height={height} action={action}>
      {data.length === 0 ? (
        <EmptyState title="No records in range" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout={layout} margin={{ top: 4, right: 34, bottom: 4, left: vertical ? 4 : 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F7" horizontal={!vertical} vertical={vertical} />
            {vertical ? (
              <>
                <XAxis type="number" tick={AXIS} allowDecimals={false} />
                <YAxis type="category" dataKey="name" tick={AXIS} width={124} interval={0} />
              </>
            ) : (
              <>
                <XAxis dataKey="name" tick={AXIS} interval={0} angle={data.length > 6 ? -18 : 0} textAnchor={data.length > 6 ? 'end' : 'middle'} height={data.length > 6 ? 42 : 24} />
                <YAxis tick={AXIS} allowDecimals={false} />
              </>
            )}
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(value: number) => [`${value}${unit ? ` ${unit}` : ''}`, 'Count']}
            />
            <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} maxBarSize={38}>
              {colorByIndex
                ? data.map((row, index) => (
                    <Cell key={row.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))
                : null}
              {data.length <= 8 ? <LabelList dataKey="value" position={vertical ? 'right' : 'top'} style={{ fontSize: 10, fill: '#475569' }} /> : null}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  )
}

export function Donut({
  data,
  testId,
  title,
  subtitle,
  height = 220,
  action,
  colors,
}: {
  data: SeriesRow[]
  testId: string
  title: string
  subtitle?: string
  height?: number
  action?: ReactNode
  colors?: string[]
}) {
  const total = data.reduce((sum, row) => sum + row.value, 0)
  return (
    <ChartFrame title={title} subtitle={subtitle} testId={testId} height={height} action={action}>
      {total === 0 ? (
        <EmptyState title="No records in range" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius="52%"
              outerRadius="80%"
              paddingAngle={1.5}
              stroke="#fff"
              strokeWidth={1.5}
            >
              {data.map((row, index) => (
                <Cell
                  key={row.name}
                  fill={(colors ?? CHART_COLORS)[index % (colors ?? CHART_COLORS).length]}
                />
              ))}
            </Pie>
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(value: number, name: string) => [
                `${value} (${total ? ((value / total) * 100).toFixed(1) : '0.0'}%)`,
                name,
              ]}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
          </PieChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  )
}

export function TrendLine({
  data,
  testId,
  title,
  subtitle,
  color = CHART_COLORS[0],
  height = 220,
  action,
}: {
  data: { week: string; count: number }[]
  testId: string
  title: string
  subtitle?: string
  color?: string
  height?: number
  action?: ReactNode
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} testId={testId} height={height} action={action}>
      {data.length === 0 ? (
        <EmptyState title="No records in range" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F7" />
            <XAxis dataKey="week" tick={AXIS} />
            <YAxis tick={AXIS} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(value: number) => [`${value} tickets`, 'Volume']} />
            <Line type="monotone" dataKey="count" stroke={color} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  )
}

export function StackedStates({
  data,
  testId,
  title,
  subtitle,
  height = 220,
}: {
  data: { name: string; healthy: number; at_risk: number; breached: number }[]
  testId: string
  title: string
  subtitle?: string
  height?: number
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} testId={testId} height={height}>
      {data.length === 0 ? (
        <EmptyState title="No records in range" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F7" />
            <XAxis dataKey="name" tick={AXIS} />
            <YAxis tick={AXIS} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
            <Bar dataKey="healthy" name="Healthy" stackId="s" fill="#10B981" maxBarSize={44} />
            <Bar dataKey="at_risk" name="At risk" stackId="s" fill="#F59E0B" maxBarSize={44} />
            <Bar dataKey="breached" name="Breached" stackId="s" fill="#EF4444" radius={[4, 4, 0, 0]} maxBarSize={44} />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  )
}

export function ScatterPlot({
  data,
  testId,
  title,
  subtitle,
  xLabel,
  yLabel,
  height = 240,
}: {
  data: { name: string; x: number; y: number; z?: number }[]
  testId: string
  title: string
  subtitle?: string
  xLabel: string
  yLabel: string
  height?: number
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} testId={testId} height={height}>
      {data.length === 0 ? (
        <EmptyState title="No agents in range" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 18, bottom: 22, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F7" />
            <XAxis type="number" dataKey="x" name={xLabel} tick={AXIS} label={{ value: xLabel, position: 'insideBottom', offset: -12, fontSize: 11, fill: '#64748B' }} />
            <YAxis type="number" dataKey="y" name={yLabel} tick={AXIS} />
            <ZAxis type="number" dataKey="z" range={[60, 200]} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              cursor={{ strokeDasharray: '3 3' }}
              formatter={(value: number, name: string) => [value, name]}
              labelFormatter={() => ''}
              content={({ payload }) => {
                const point = payload?.[0]?.payload as { name: string; x: number; y: number } | undefined
                if (!point) return null
                return (
                  <div style={TOOLTIP_STYLE} className="bg-white px-2 py-1">
                    <p className="font-semibold">{point.name}</p>
                    <p className="text-[11px]">
                      {xLabel}: {point.x} · {yLabel}: {point.y}
                    </p>
                  </div>
                )
              }}
            />
            <Scatter data={data} fill={CHART_COLORS[0]}>
              {data.map((row, index) => (
                <Cell key={row.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  )
}

export function RadialScore({
  data,
  testId,
  title,
  subtitle,
  height = 200,
}: {
  data: { name: string; value: number; fill: string }[]
  testId: string
  title: string
  subtitle?: string
  height?: number
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} testId={testId} height={height}>
      {data.length === 0 ? (
        <EmptyState title="No candidate selected" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart data={data} innerRadius="28%" outerRadius="96%" startAngle={90} endAngle={-270}>
            <RadialBar dataKey="value" cornerRadius={4} background={{ fill: '#F1F5F9' }} />
            <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(value: number) => [`${value.toFixed(2)} pts`, 'Contribution']} />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
          </RadialBarChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  )
}

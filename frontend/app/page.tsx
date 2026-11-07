"use client"

import Link from "next/link"
import { motion } from "motion/react"
import {
  Bot,
  Brain,
  Cpu,
  FileCheck,
  Network,
  Settings,
  Upload,
  Workflow,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

const steps = [
  {
    icon: Settings,
    title: "Configure Workflows",
    description:
      "Define your business rules, compliance requirements, and validation logic once. The AI learns your processes and adapts.",
  },
  {
    icon: Upload,
    title: "Upload Documents",
    description:
      "Attach case documents and reference files for a configured review workflow.",
  },
  {
    icon: Network,
    title: "AI Swarm Activates",
    description:
      "A case orchestrator delegates configured categories to evaluator agents and streams their progress.",
  },
]

const features = [
  {
    icon: Brain,
    title: "AI Agent Swarm",
    description:
      "Coordinate category-focused evaluator agents around the rules in your workflow.",
  },
  {
    icon: Settings,
    title: "Flexible Configuration",
    description:
      "Group review rules into reusable categories, then apply the workflow to case submissions.",
  },
  {
    icon: Upload,
    title: "Universal Document Processing",
    description:
      "Upload any format — PDFs, images, spreadsheets, forms, CAD files. AI extracts and analyzes all information.",
  },
  {
    icon: Workflow,
    title: "Automated Workflows",
    description:
      "Each agent handles specific tasks in parallel. From data extraction to validation to approval routing.",
  },
  {
    icon: FileCheck,
    title: "Instant Verification",
    description:
      "Real-time validation against your custom rules and industry regulations with detailed audit reports.",
  },
  {
    icon: Cpu,
    title: "Smart Task Distribution",
    description:
      "AI intelligently assigns tasks to specialized agents based on document type, content, and your workflow logic.",
  },
]

const useCases = [
  {
    title: "Building & Permit Approvals",
    description:
      "Automate plan reviews, zoning checks, and compliance verification for government agencies.",
  },
  {
    title: "Legal Document Review",
    description:
      "Process contracts, agreements, and legal filings with multi-agent verification workflows.",
  },
  {
    title: "Healthcare Claims Processing",
    description:
      "Validate medical claims, check policy compliance, and route approvals automatically.",
  },
  {
    title: "Financial Auditing",
    description:
      "Audit financial statements, tax documents, and compliance reports with specialized agents.",
  },
  {
    title: "Customer Support",
    description:
      "Deploy agent swarms to triage, categorize, and respond to customer inquiries in real-time.",
  },
  {
    title: "Data Quality & Migration",
    description:
      "Validate, clean, and migrate large datasets with parallel AI verification agents.",
  },
]

const stats = [
  { value: "Rules", label: "Configurable Categories" },
  { value: "Live", label: "Agent Progress" },
  { value: "Review", label: "Structured Findings" },
]

export default function Page() {
  return (
    <div className="min-h-screen text-[#1d1d1f] relative">
      {/* Hero */}
      <section className="container mx-auto px-4 py-20 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <Badge
            variant="outline"
            className="border-[#1d1d1f]/15 text-[#1d1d1f] bg-[#1d1d1f]/5 mb-6 shadow-depth-1"
          >
            <Network className="size-4 mr-2" />
            AI Agent Swarm Technology
          </Badge>

          <h1 className="text-5xl md:text-7xl font-black mb-6 leading-[1.05]">
            <span className="text-[#1d1d1f]">Deploy AI Agent Swarms</span>
            <br />
            <span className="text-[#86868b]">For Any Workflow</span>
          </h1>

          <p className="text-xl text-[#86868b] max-w-3xl mx-auto mb-8">
            Define review rules, attach case documents, and follow a case orchestrator as it delegates category checks and streams findings for human review.
          </p>

          <div className="flex items-center justify-center gap-4 flex-wrap">
            <Link href="/workflows">
              <Button
                size="lg"
                className="bg-[#1d1d1f] text-white hover:bg-[#424245] text-lg px-8 shadow-depth-2"
              >
                Start Free Trial
              </Button>
            </Link>
            <Button
              size="lg"
              variant="outline"
              className="glass-card border-[#1d1d1f]/15 text-[#1d1d1f] hover:shadow-depth-2 transition-all text-lg px-8"
            >
              Watch Demo
            </Button>
          </div>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="grid grid-cols-3 gap-4 max-w-3xl mx-auto mt-16"
        >
          {stats.map((stat) => (
            <Card
              key={stat.label}
              className="glass-card hover:shadow-depth-2 transition-all cursor-pointer group"
            >
              <CardContent className="p-6 text-center">
                <div className="text-3xl font-bold text-[#1d1d1f] mb-1 group-hover:scale-110 transition-transform">
                  {stat.value}
                </div>
                <div className="text-xs text-[#86868b]">{stat.label}</div>
              </CardContent>
            </Card>
          ))}
        </motion.div>
      </section>

      {/* How it works + features */}
      <section className="container mx-auto px-4 py-20">
        <h2 className="text-4xl font-bold text-center mb-4">
          <span className="text-[#1d1d1f]">How AI Agent Swarm Works</span>
        </h2>
        <p className="text-center text-[#86868b] mb-16 max-w-2xl mx-auto">
          Configure categories and rules, then follow orchestrator and evaluator activity in one review interface.
        </p>

        <div className="grid md:grid-cols-3 gap-8 mb-20">
          {steps.map((step, index) => (
            <motion.div
              key={step.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: index * 0.1 }}
              className="relative"
            >
              <Card className="glass-card hover:shadow-depth-2 transition-all h-full group">
                <CardHeader>
                  <div className="size-12 rounded-lg bg-[#1d1d1f] flex items-center justify-center mb-4 group-hover:scale-110 transition-transform shadow-depth-2">
                    <step.icon className="size-6 text-white" />
                  </div>
                  <Badge
                    variant="outline"
                    className="border-[#1d1d1f]/15 text-[#1d1d1f] bg-[#1d1d1f]/5 w-fit mb-2"
                  >
                    STEP {index + 1}
                  </Badge>
                  <CardTitle className="text-[#1d1d1f]">{step.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-[#86868b]">
                    {step.description}
                  </CardDescription>
                </CardContent>
              </Card>
              {index < steps.length - 1 && (
                <div className="hidden md:block absolute top-1/2 -right-4 transform -translate-y-1/2">
                  <div className="w-8 h-0.5 bg-black/[0.06]" />
                </div>
              )}
            </motion.div>
          ))}
        </div>

        <h2 className="text-4xl font-bold text-center mb-16">
          <span className="text-[#1d1d1f]">Powerful Features for Any Industry</span>
        </h2>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: index * 0.1 }}
            >
              <Card className="glass-card hover:shadow-depth-2 transition-all h-full group">
                <CardHeader>
                  <div className="size-12 rounded-lg bg-[#1d1d1f]/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                    <feature.icon className="size-6 text-[#1d1d1f]" />
                  </div>
                  <CardTitle className="text-[#1d1d1f]">{feature.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-[#86868b]">
                    {feature.description}
                  </CardDescription>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Use cases */}
      <section className="container mx-auto px-4 py-20">
        <h2 className="text-4xl font-bold text-center mb-4">
          <span className="text-[#1d1d1f]">Explore Review Workflows</span>
        </h2>
        <p className="text-center text-[#86868b] mb-16 max-w-2xl mx-auto">
          AI agent swarms adapt to any workflow — from compliance to customer service
        </p>

        <div className="grid md:grid-cols-3 gap-6 mb-20">
          {useCases.map((useCase, index) => (
            <motion.div
              key={useCase.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: index * 0.1 }}
            >
              <Card className="glass-card hover:shadow-depth-2 transition-all h-full group cursor-pointer">
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold text-[#1d1d1f] mb-2">
                    {useCase.title}
                  </h3>
                  <p className="text-sm text-[#86868b]">{useCase.description}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto px-4 py-20">
        <Card className="glass-card shadow-depth-3">
          <CardContent className="p-12 text-center">
            <h2 className="text-4xl font-bold mb-4 text-[#1d1d1f]">
              Ready to Deploy AI Agent Swarms?
            </h2>
            <p className="text-xl text-[#86868b] mb-8">
              Join organizations using agentic AI to transform their workflows and save 90% of processing time.
            </p>
            <Link href="/workflows">
              <Button
                size="lg"
                className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all text-lg px-8"
              >
                Get Started for Free
              </Button>
            </Link>
          </CardContent>
        </Card>
      </section>

      {/* Footer */}
      <footer className="border-t border-black/[0.08] py-8 bg-white/80 backdrop-blur-sm">
        <div className="container mx-auto px-4 flex items-center justify-center gap-3 text-[#86868b] text-sm">
          <div className="size-5 rounded-md bg-[#1d1d1f] flex items-center justify-center">
            <Bot className="size-3 text-white" />
          </div>
          <span>© 2026 PlanAI. All rights reserved.</span>
        </div>
      </footer>
    </div>
  )
}

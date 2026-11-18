import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'

import { useAuth } from '@/features/auth/context'
import { api } from '@/lib/api'

interface Profile {
  full_name: string | null
  skills: { name: string }[]
  experience_years: number | null
  location: string | null
}

/** 8A: real profile basics + what to do next. The full dashboard (matches, activity) is 8C. */
export default function Overview() {
  const { account } = useAuth()
  const { data: profile, isLoading } = useQuery({ queryKey: ['profile'], queryFn: () => api<Profile>('/candidates/me') })
  const missing = profile
    ? [!profile.skills.length && 'skills', profile.experience_years == null && 'experience', !profile.location && 'location'].filter(Boolean)
    : []
  return (
    <div className="max-w-3xl">
      <h1 className="text-h1 font-semibold tracking-[-0.03em]">
        {profile?.full_name ? `Hello, ${profile.full_name.split(' ')[0]}.` : 'Welcome.'}
      </h1>
      <p className="mt-2 text-muted-foreground">Signed in as {account?.email}.</p>
      {isLoading ? <p className="mt-8 text-muted-foreground">Loading your profile…</p> : (
        <section aria-labelledby="next" className="mt-10 rounded-lg border border-line bg-card p-6">
          <h2 id="next" className="text-h3 font-semibold tracking-tight">
            {missing.length ? 'Finish your profile to get ranked matches' : 'Your profile is ready'}
          </h2>
          <p className="mt-2 max-w-[60ch] text-muted-foreground">
            {missing.length
              ? `Still missing: ${missing.join(', ')}. The fastest way is to upload your résumé. You review what we extract before anything is saved.`
              : `${profile!.skills.length} skills on file. Your ranked matches are ready.`}
          </p>
          <Link to="/app/resume" className="mt-5 inline-flex rounded-md bg-primary px-4 py-2 text-small font-semibold text-primary-foreground">
            Upload your résumé
          </Link>
        </section>
      )}
    </div>
  )
}

import { withSupabase } from "@supabase/server";

export default {
  fetch: withSupabase({ auth: "publishable" }, async (_req, ctx) => {
    return Response.json({
      ok: true,
      authMode: ctx.authMode,
      authKeyName: ctx.authKeyName ?? null,
    });
  }),
};

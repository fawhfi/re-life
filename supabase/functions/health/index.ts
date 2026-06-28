import { withSupabase } from "@supabase/server";

export default {
  fetch: withSupabase({ auth: "none" }, async (_req, ctx) => {
    return Response.json({
      ok: true,
      authMode: ctx.authMode,
    });
  }),
};

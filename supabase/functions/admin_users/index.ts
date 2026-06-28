import { withSupabase } from "@supabase/server";

export default {
  fetch: withSupabase({ auth: "secret" }, async (_req, ctx) => {
    const { data: users, error } = await ctx.supabaseAdmin
      .from("app_users")
      .select("id,public_id,display_name,email,photo_url,created_at")
      .order("created_at", { ascending: false })
      .limit(50);

    if (error) {
      return Response.json({ error: error.message }, { status: 400 });
    }

    return Response.json({ users: users ?? [] });
  }),
};

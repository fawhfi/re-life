import { withSupabase } from "@supabase/server";

export default {
  fetch: withSupabase({ auth: "user" }, async (_req, ctx) => {
    const { data: authUser, error: authError } = await ctx.supabase.auth.getUser();
    if (authError || !authUser.user) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { data: records, error } = await ctx.supabase
      .from("scan_records")
      .select("id,mode,name,description,material,grade,overall_score,created_at")
      .order("created_at", { ascending: false })
      .limit(20);

    if (error) {
      return Response.json({ error: error.message }, { status: 400 });
    }

    return Response.json({
      user: {
        id: authUser.user.id,
        email: authUser.user.email,
      },
      records: records ?? [],
    });
  }),
};

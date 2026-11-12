import { useSignUp } from "@/api/use-sign-up";
import { describeCredentialsMutation } from "../helpers/credentials-mutation-suite";

describeCredentialsMutation({
	name: "useSignUp",
	path: "/api/v1/auth/setup",
	useHook: useSignUp,
	failure: { status: 409, code: "setup_already_done" },
});

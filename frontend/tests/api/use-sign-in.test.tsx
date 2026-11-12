import { useSignIn } from "@/api/use-sign-in";
import { describeCredentialsMutation } from "../helpers/credentials-mutation-suite";

describeCredentialsMutation({
	name: "useSignIn",
	path: "/api/v1/auth/login",
	useHook: useSignIn,
	failure: { status: 401, code: "invalid_credentials" },
});

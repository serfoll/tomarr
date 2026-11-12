import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// jsdom has no scrollTo and logs "Not implemented" when the router restores scroll.
window.scrollTo = () => {};

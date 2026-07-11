import { Router, type IRouter } from "express";
import healthRouter from "./health";
import approvalsRouter from "./approvals";
import configRouter from "./config";

const router: IRouter = Router();

router.use(healthRouter);
router.use(approvalsRouter);
router.use(configRouter);

export default router;

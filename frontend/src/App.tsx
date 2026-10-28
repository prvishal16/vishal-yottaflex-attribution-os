import { lazy } from "react";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";

const OverviewPage = lazy(() =>
  import("./pages/OverviewPage").then((module) => ({ default: module.OverviewPage })),
);
const CampaignsPage = lazy(() =>
  import("./pages/CampaignsPage").then((module) => ({ default: module.CampaignsPage })),
);
const CampaignDetailPage = lazy(() =>
  import("./pages/CampaignDetailPage").then((module) => ({ default: module.CampaignDetailPage })),
);
const JourneyPage = lazy(() =>
  import("./pages/JourneyPage").then((module) => ({ default: module.JourneyPage })),
);
const DataQualityPage = lazy(() =>
  import("./pages/DataQualityPage").then((module) => ({ default: module.DataQualityPage })),
);
const RunsPage = lazy(() =>
  import("./pages/RunsPage").then((module) => ({ default: module.RunsPage })),
);
const NotFoundPage = lazy(() =>
  import("./pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })),
);

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="campaigns" element={<CampaignsPage />} />
        <Route path="campaigns/:campaignId" element={<CampaignDetailPage />} />
        <Route path="journeys" element={<JourneyPage />} />
        <Route path="data-quality" element={<DataQualityPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

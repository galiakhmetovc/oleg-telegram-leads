import { Box, Typography } from "@mui/material";

export function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <Box className="analytics-kpi">
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>
        {value}
      </Typography>
    </Box>
  );
}

export function SectionTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {subtitle}
      </Typography>
    </Box>
  );
}

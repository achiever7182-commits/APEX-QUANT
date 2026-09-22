export const MOCK_MODELS = [
  { 
    name: "Ridge Walk-Forward L2", 
    version: "v1.4", 
    status: "ACTIVE", 
    trainingWindow: "Expanding", 
    features: 66, 
    horizon: "5d", 
    confidence: 0.85, 
    valIc: 0.045, 
    valMae: 0.012 
  },
  { 
    name: "Random Forest Quant", 
    version: "v2.1", 
    status: "VALIDATING", 
    trainingWindow: "Rolling 2Y", 
    features: 102, 
    horizon: "5d", 
    confidence: 0.65, 
    valIc: 0.038, 
    valMae: 0.014 
  },
  { 
    name: "Gradient Boosting V3", 
    version: "v3.0", 
    status: "RESEARCH", 
    trainingWindow: "Rolling 1Y", 
    features: 120, 
    horizon: "1d", 
    confidence: 0.42, 
    valIc: 0.021, 
    valMae: 0.018 
  },
];

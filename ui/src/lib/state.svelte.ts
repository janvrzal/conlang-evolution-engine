// Sdílený stav aplikace pro předávání vygenerovaných dat mezi Metaeditací a Mapou
export const projectState = $state<{
	generatedProtoLexicon: any[];
	simulationResult: any | null;
}>({
	generatedProtoLexicon: [],
	simulationResult: null
});

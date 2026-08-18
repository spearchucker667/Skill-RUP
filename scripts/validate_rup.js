#!/usr/bin/env node
/**
 * RUP Protocol Validator v3.0.0 - Node.js Script
 *
 * Validates RUP protocol YAML files and agent outputs against the JSON Schema.
 *
 * Usage:
 *   node validate_rup.js protocol <protocol.yaml>
 *   node validate_rup.js output <output.json> <discovery|plan|execution|verification>
 *   node validate_rup.js all <directory>
 *
 * Requirements:
 *   npm install ajv ajv-formats js-yaml glob
 *
 * Author: Faye Håkansdotter
 * License: CC0-1.0
 */

const fs = require('fs');
const path = require('path');

function envInt(name, defaultValue) {
    const raw = process.env[name];
    if (!raw) return defaultValue;
    const parsed = parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : defaultValue;
}

const MAX_FILE_BYTES = envInt('RUP_MAX_FILE_BYTES', 5 * 1024 * 1024);
const MAX_YAML_ALIASES = envInt('RUP_MAX_YAML_ALIASES', 50);

function readFileWithLimit(filePath) {
    const stats = fs.statSync(filePath);
    if (stats.size > MAX_FILE_BYTES) {
        throw new Error(`File too large: ${filePath} (${stats.size} bytes > ${MAX_FILE_BYTES} bytes)`);
    }
    return fs.readFileSync(filePath, 'utf8');
}

// Check for required modules
let Ajv, addFormats, yaml, glob;
try {
    Ajv = require('ajv/dist/2020');
    addFormats = require('ajv-formats');
    yaml = require('js-yaml');
    glob = require('glob');
} catch (e) {
    console.error('Missing required modules. Install with:');
    console.error('  npm install ajv ajv-formats js-yaml glob');
    process.exit(1);
}

// Colors for terminal output
const colors = {
    red: '\x1b[91m',
    green: '\x1b[92m',
    yellow: '\x1b[93m',
    blue: '\x1b[94m',
    cyan: '\x1b[96m',
    bold: '\x1b[1m',
    reset: '\x1b[0m'
};

/**
 * Add ANSI color codes to text if the terminal supports it.
 * @param {string} text - The text to colorize.
 * @param {string} color - The color key from the colors object.
 * @returns {string} Colorized text or the original text if not a TTY.
 */
function colorize(text, color) {
    if (process.stdout.isTTY) {
        return `${colors[color]}${text}${colors.reset}`;
    }
    return text;
}

function printSuccess(message) {
    console.log(`${colorize('✓', 'green')} ${message}`);
}

function printError(message) {
    console.log(`${colorize('✗', 'red')} ${message}`);
}

function printWarning(message) {
    console.log(`${colorize('⚠', 'yellow')} ${message}`);
}

function printInfo(message) {
    console.log(`${colorize('ℹ', 'blue')} ${message}`);
}

// Load schema
/**
 * Load the RUP JSON Schema from the specified path or default location.
 * @param {string|null} schemaPath - Path to the schema file, or null for default.
 * @returns {Object} Parsed JSON schema object.
 * @throws {Error} If the schema file is not found.
 */
function loadSchema(schemaPath) {
    if (!schemaPath) {
        schemaPath = path.join(__dirname, '..', 'rup-schema.json');
    }

    if (!fs.existsSync(schemaPath)) {
        throw new Error(`Schema not found: ${schemaPath}`);
    }

    return JSON.parse(readFileWithLimit(schemaPath));
}

// Load YAML file
/**
 * Load and parse a YAML file.
 * @param {string} filePath - Path to the YAML file.
 * @returns {Object} Parsed YAML content.
 * @throws {Error} If the file is not found.
 */
function loadYaml(filePath) {
    if (!fs.existsSync(filePath)) {
        throw new Error(`File not found: ${filePath}`);
    }

    return yaml.load(readFileWithLimit(filePath), { maxAliasCount: MAX_YAML_ALIASES });
}

// Load JSON file
/**
 * Load and parse a JSON file.
 * @param {string} filePath - Path to the JSON file.
 * @returns {Object} Parsed JSON content.
 * @throws {Error} If the file is not found.
 */
function loadJson(filePath) {
    if (!fs.existsSync(filePath)) {
        throw new Error(`File not found: ${filePath}`);
    }

    return JSON.parse(readFileWithLimit(filePath));
}

// Format validation error
/**
 * Format a validation error for terminal display.
 * @param {Object} error - AJV validation error object.
 * @param {number} [indent=0] - Indentation level.
 * @returns {string} Formatted error string.
 */
function formatError(error, indent = 0) {
    const prefix = '  '.repeat(indent);
    const path = error.instancePath || '(root)';

    let lines = [
        `${prefix}${colorize('✗', 'red')} ${colorize(path, 'cyan')}`,
        `${prefix}  Message: ${error.message}`
    ];

    if (error.keyword) {
        lines.push(`${prefix}  Keyword: ${error.keyword}`);
    }

    if (error.params && Object.keys(error.params).length > 0) {
        const params = JSON.stringify(error.params);
        if (params.length < 100) {
            lines.push(`${prefix}  Params: ${params}`);
        }
    }

    return lines.join('\n');
}

// Create AJV validator
/**
 * Create an AJV validator instance configured for the RUP schema.
 * @param {Object} schema - JSON Schema object.
 * @returns {Function} Compiled AJV validate function.
 */
function createValidator(schema) {
    const ajv = new Ajv({
        allErrors: true,
        strict: false,
        validateFormats: true
    });
    addFormats(ajv);

    return ajv.compile(schema);
}

// Validate protocol
/**
 * Validate a RUP protocol YAML file against the schema.
 * @param {string} protocolPath - Path to the protocol YAML file.
 * @param {string|null} schemaPath - Path to the schema file, or null for default.
 * @returns {{valid: boolean, errors: Array}} Validation result object.
 */
function validateProtocol(protocolPath, schemaPath) {
    try {
        const schema = loadSchema(schemaPath);
        const protocol = loadYaml(protocolPath);

        // Enforce schema version (derive expected version from the schema $id).
        // This keeps the validator behavior consistent when the schema is upgraded.
        let expectedVersion = null;
        if (schema && typeof schema.x_rup_schema_version === 'string') {
            expectedVersion = schema.x_rup_schema_version;
        } else if (schema && typeof schema.$id === 'string') {
            const m = schema.$id.match(/\/v(\d+\.\d+\.\d+)\//);
            if (m) expectedVersion = m[1];
        }

        if (expectedVersion && protocol.schema_version && protocol.schema_version !== expectedVersion) {
             printError(`Protocol validation failed: ${protocolPath}`);
             console.log(`  Found 1 error(s):`);
             console.log(`  ${colorize('✗', 'red')} ${colorize('/schema_version', 'cyan')}`);
             console.log(`    Message: Schema version mismatch. Expected ${expectedVersion}, got ${protocol.schema_version}`);
             return { valid: false, errors: [{ message: "Schema version mismatch" }] };
        }

        const validate = createValidator(schema);
        const valid = validate(protocol);

        if (valid) {
            console.log(`${colorize('✓', 'green')} ${colorize(protocolPath, 'bold')}: ${colorize('Valid', 'green')}`);
            return { valid: true, errors: [] };
        } else {
            console.log(`${colorize('✗', 'red')} ${colorize(protocolPath, 'bold')}: ${colorize('Invalid', 'red')}`);
            console.log(`  Found ${validate.errors.length} error(s):`);

            validate.errors.slice(0, 10).forEach(error => {
                console.log(formatError(error, 1));
            });

            if (validate.errors.length > 10) {
                console.log(`  ... and ${validate.errors.length - 10} more errors`);
            }

            return { valid: false, errors: validate.errors };
        }
    } catch (e) {
        printError(`Error: ${e.message}`);
        return { valid: false, errors: [e] };
    }
}

// Validate agent output
/**
 * Validate an agent output JSON file against the appropriate sub-schema.
 * @param {string} outputPath - Path to the output JSON file.
 * @param {string} outputType - Type of output (discovery|plan|execution|verification).
 * @param {string|null} schemaPath - Path to the schema file, or null for default.
 * @returns {{valid: boolean, errors: Array}} Validation result object.
 */
function validateOutput(outputPath, outputType, schemaPath) {
    const typeMap = {
        'discovery': 'DiscoveryReport',
        'plan': 'PlanOutput',
        'execution': 'ExecutionOutput',
        'verification': 'VerificationOutput'
    };

    if (!typeMap[outputType]) {
        printError(`Unknown output type: ${outputType}`);
        console.log(`Valid types: ${Object.keys(typeMap).join(', ')}`);
        return { valid: false, errors: [] };
    }

    try {
        const schema = loadSchema(schemaPath);
        const output = loadJson(outputPath);

        const defName = typeMap[outputType];

        if (!schema.$defs || !schema.$defs[defName]) {
            printError(`Schema definition not found: ${defName}`);
            return { valid: false, errors: [] };
        }

        // Create sub-schema with definitions
        const subSchema = {
            ...schema.$defs[defName],
            $defs: schema.$defs
        };

        const validate = createValidator(subSchema);
        const valid = validate(output);

        if (valid) {
            console.log(`${colorize('✓', 'green')} ${colorize(outputPath, 'bold')}: ${colorize('Valid', 'green')}`);
            return { valid: true, errors: [] };
        } else {
            console.log(`${colorize('✗', 'red')} ${colorize(outputPath, 'bold')}: ${colorize('Invalid', 'red')}`);
            console.log(`  Found ${validate.errors.length} error(s):`);

            validate.errors.slice(0, 10).forEach(error => {
                console.log(formatError(error, 1));
            });

            if (validate.errors.length > 10) {
                console.log(`  ... and ${validate.errors.length - 10} more errors`);
            }

            return { valid: false, errors: validate.errors };
        }
    } catch (e) {
        printError(`Error: ${e.message}`);
        return { valid: false, errors: [e] };
    }
}

// Validate all files in directory
/**
 * Validate all protocol and output files in a directory.
 * @param {string} directory - Path to the directory to scan.
 * @param {string|null} schemaPath - Path to the schema file, or null for default.
 * @returns {{valid: boolean, results: Array}} Validation results object.
 */
function validateAll(directory, schemaPath) {
    if (!fs.existsSync(directory) || !fs.statSync(directory).isDirectory()) {
        printError(`Directory not found: ${directory}`);
        return { valid: false, results: [] };
    }

    console.log(colorize('Validation Results', 'bold'));
    console.log('═'.repeat(50));

    const results = [];

    // Find protocol files
    const protocolFiles = glob.sync(`${directory}/**/*protocol*.{yaml,yml}`, { nodir: true });
    protocolFiles.forEach(file => {
        const result = validateProtocol(file, schemaPath);
        results.push({ file, ...result });
    });

    // Find output files
    const outputPatterns = [
        { type: 'discovery', pattern: '**/discovery*.json' },
        { type: 'plan', pattern: '**/plan*.json' },
        { type: 'execution', pattern: '**/execution*.json' },
        { type: 'execution', pattern: '**/changes*.json' },
        { type: 'verification', pattern: '**/verification*.json' },
        { type: 'verification', pattern: '**/report*.json' }
    ];

    outputPatterns.forEach(({ type, pattern }) => {
        const files = glob.sync(`${directory}/${pattern}`, { nodir: true });
        files.forEach(file => {
            const result = validateOutput(file, type, schemaPath);
            results.push({ file, type, ...result });
        });
    });

    console.log('═'.repeat(50));

    const validCount = results.filter(r => r.valid).length;
    const invalidCount = results.filter(r => !r.valid).length;

    console.log(`Total: ${results.length} files`);
    printSuccess(`Valid: ${validCount}`);
    if (invalidCount > 0) {
        printError(`Invalid: ${invalidCount}`);
    }

    return {
        valid: invalidCount === 0,
        results
    };
}

// Generate sample output
/**
 * Generate a sample output file for a given type.
 * @param {string} outputType - Type of sample (discovery|plan|execution|verification).
 * @param {string|null} outputPath - Output file path, or null for default naming.
 * @returns {boolean} True if sample was created successfully.
 */
function generateSample(outputType, outputPath) {
    const samples = {
        discovery: {
            repo_metadata: {
                name: "sample-repo",
                primary_language: "python",
                repo_type: "library",
                loc: 5000,
                file_count: 42
            },
            languages: [
                { name: "python", percentage: 85.5, lockfile_present: true }
            ],
            tooling: {
                test_framework: "pytest",
                linter: "ruff"
            },
            gaps: [
                {
                    id: "TEST-001",
                    category: "tests",
                    severity: "high",
                    title: "Low test coverage"
                }
            ],
            risk_assessment: {
                overall_risk: "medium",
                technical_debt_score: 35,
                production_readiness_score: 65
            }
        },
        plan: {
            backlog: [
                {
                    id: "ITEM-001",
                    priority: "P0",
                    title: "Add missing tests"
                }
            ],
            selected_items: ["ITEM-001"],
            execution_order: ["ITEM-001"],
            estimated_effort: {
                total_minutes: 60,
                confidence: "medium"
            }
        },
        execution: {
            changes: [
                {
                    file_path: "tests/test_main.py",
                    change_type: "create"
                }
            ],
            commits: [
                {
                    message: "test: add unit tests for main module",
                    files: ["tests/test_main.py"]
                }
            ],
            local_verification: {
                tests: { executed: true, passed: true },
                lint: { executed: true, passed: true }
            }
        },
        verification: {
            verification_results: {
                overall_status: "passed"
            },
            metrics: {
                files_changed: 1,
                lines_added: 50
            },
            recommendations: {
                ready_for_pr: true
            }
        }
    };

    if (!samples[outputType]) {
        printError(`Unknown output type: ${outputType}`);
        return false;
    }

    const filePath = outputPath || `sample_${outputType}.json`;
    fs.writeFileSync(filePath, JSON.stringify(samples[outputType], null, 2));
    printSuccess(`Created sample ${outputType} output: ${filePath}`);
    return true;
}

// Print usage
function printUsage() {
    console.log(`
${colorize('RUP Protocol Validator v3.0.0', 'bold')}

${colorize('Usage:', 'bold')}
    node validate_rup.js protocol <protocol.yaml>
    node validate_rup.js output <file.json> <type>
    node validate_rup.js all <directory>
    node validate_rup.js sample <type> [output.json]
    node validate_rup.js help

${colorize('Output Types:', 'bold')}
    discovery       Discovery agent output
    plan            Planning agent output
    execution       Execution agent output
    verification    Verification agent output

${colorize('Examples:', 'bold')}
    node validate_rup.js protocol rup-protocol.yaml
    node validate_rup.js output discovery.json discovery
    node validate_rup.js all ./my-project
    node validate_rup.js sample discovery

${colorize('Environment Variables:', 'bold')}
    RUP_SCHEMA_PATH     Path to rup-schema.json
`);
}

// Main entry point
function main() {
    const args = process.argv.slice(2);
    
    // Manual argument parsing to support flags
    const parsedArgs = {
        command: null,
        positional: [],
        schema: process.env.RUP_SCHEMA_PATH || null,
        verbose: false,
        type: null
    };

    for (let i = 0; i < args.length; i++) {
        const arg = args[i];
        if (arg === '--schema' || arg === '-s') {
            parsedArgs.schema = args[++i];
        } else if (arg === '--verbose' || arg === '-v') {
            parsedArgs.verbose = true;
        } else if (!parsedArgs.command) {
            parsedArgs.command = arg;
        } else {
            parsedArgs.positional.push(arg);
        }
    }

    const command = parsedArgs.command || 'help';
    const schemaPath = parsedArgs.schema;

    switch (command) {
        case 'protocol':
            if (parsedArgs.positional.length < 1) {
                printError('Missing protocol file argument');
                printUsage();
                process.exit(1);
            }
            const protocolResult = validateProtocol(parsedArgs.positional[0], schemaPath);
            process.exit(protocolResult.valid ? 0 : 1);
            break;

        case 'output':
            if (parsedArgs.positional.length < 2) {
                printError('Missing arguments');
                printUsage();
                process.exit(1);
            }
            const outputResult = validateOutput(parsedArgs.positional[0], parsedArgs.positional[1], schemaPath);
            process.exit(outputResult.valid ? 0 : 1);
            break;

        case 'all':
            if (parsedArgs.positional.length < 1) {
                printError('Missing directory argument');
                printUsage();
                process.exit(1);
            }
            const allResult = validateAll(parsedArgs.positional[0], schemaPath);
            process.exit(allResult.valid ? 0 : 1);
            break;

        case 'sample':
            if (parsedArgs.positional.length < 1) {
                printError('Missing output type argument');
                printUsage();
                process.exit(1);
            }
            const sampleResult = generateSample(parsedArgs.positional[0], parsedArgs.positional[1]);
            process.exit(sampleResult ? 0 : 1);
            break;

        case 'help':
        case '--help':
        case '-h':
            printUsage();
            process.exit(0);
            break;

        default:
            printError(`Unknown command: ${command}`);
            printUsage();
            process.exit(1);
    }
}

main();

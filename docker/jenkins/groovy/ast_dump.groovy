/*
 * j2gha Groovy AST dumper.
 *
 * Parses Jenkinsfiles / shared-library sources with the *same* Groovy version that Jenkins
 * bundles (groovy-all 2.4.x inside jenkins.war) up to the CONVERSION phase and emits a
 * JSON projection of the AST that is convenient for pipeline analysis:
 *   - every method call becomes a "call" node (name, receiver, positional/named args, closure body)
 *   - control flow (if/for/while/try/switch) is preserved with nested statements
 *   - every node carries line/column provenance
 *
 * Usage: java -cp groovy-all.jar groovy.ui.GroovyMain ast_dump.groovy [--out DIR] FILE...
 * Without --out a JSON array is written to stdout.
 * Must remain compatible with Groovy 2.4 (no lambdas, no var keyword, no Groovy 3 syntax).
 */
import groovy.json.JsonOutput
import org.codehaus.groovy.ast.*
import org.codehaus.groovy.ast.expr.*
import org.codehaus.groovy.ast.stmt.*
import org.codehaus.groovy.control.*
import org.codehaus.groovy.control.messages.SyntaxErrorMessage
import org.codehaus.groovy.syntax.SyntaxException

class Dumper {
    String[] lines

    Dumper(String source) {
        this.lines = source.split('\n', -1)
    }

    Map pos(ASTNode n) {
        if (n == null || n.lineNumber < 1) return [:]
        return [line: n.lineNumber, col: n.columnNumber, endLine: n.lastLineNumber, endCol: n.lastColumnNumber]
    }

    String text(ASTNode n, int max = 4000) {
        if (n instanceof BinaryExpression) {
            // CONVERSION-phase binary expressions are positioned at their operator (`return a == b` -> "=="): span
            // the operands instead, widened over the parentheses the AST drops ((a || b) && c)
            int[] s = startOf((Expression) n), e = endOf((Expression) n)
            if (s != null && e != null) return slice(balance(s, e), max)
        }
        if (n == null || n.lineNumber < 1 || n.lastLineNumber < 1) {
            try { return n?.text } catch (Throwable t) { return null }
        }
        return slice([n.lineNumber, n.columnNumber, n.lastLineNumber, n.lastColumnNumber] as int[], max)
    }

    String slice(int[] r, int max) {
        StringBuilder sb = new StringBuilder()
        for (int l = r[0]; l <= r[2] && l <= lines.length; l++) {
            String line = lines[l - 1]
            int start = (l == r[0]) ? Math.max(0, r[1] - 1) : 0
            int end = (l == r[2]) ? Math.min(line.length(), Math.max(0, r[3] - 1)) : line.length()
            if (start <= end) sb.append(line.substring(start, end))
            if (l != r[2]) sb.append('\n')
            if (sb.length() > max) { sb.delete(max, sb.length()); sb.append('...'); break }  // setLength is not dispatchable from Groovy 2.4 on a modern JDK (AbstractStringBuilder)
        }
        return sb.toString()
    }

    int[] startOf(Expression e) {
        if (e instanceof BinaryExpression) return startOf(((BinaryExpression) e).leftExpression)
        return e != null && e.lineNumber > 0 ? [e.lineNumber, e.columnNumber] as int[] : null
    }

    int[] endOf(Expression e) {
        if (e instanceof BinaryExpression) return endOf(((BinaryExpression) e).rightExpression)
        return e != null && e.lastLineNumber > 0 ? [e.lastLineNumber, e.lastColumnNumber] as int[] : null
    }

    int[] balance(int[] s, int[] e) {
        int[] r = [s[0], s[1], e[0], e[1]] as int[]
        if (r[0] > r[2] || (r[0] == r[2] && r[1] > r[3])) return r
        String t = slice(r, 100000)
        for (String pair : ['()', '[]']) {  // index expressions (a[b]) are binary too
            char o = pair.charAt(0), cl = pair.charAt(1)
            int open = t.count(o as String), close = t.count(cl as String)
            while (close > open && r[1] > 1) {  // pull the start back over whitespace and openers
                char c = lines[r[0] - 1].charAt(r[1] - 2)
                if (c == o) open++
                else if (!Character.isWhitespace(c)) break
                r[1]--
            }
            while (open > close && r[3] - 1 < lines[r[2] - 1].length()) {  // push the end over whitespace and closers
                char c = lines[r[2] - 1].charAt(r[3] - 1)
                if (c == cl) close++
                else if (!Character.isWhitespace(c)) break
                r[3]++
            }
        }
        return r
    }

    // ------------------------------------------------------------------ statements
    List stmts(Statement s) {
        List out = []
        if (s == null) return out
        if (s instanceof BlockStatement) {
            for (Statement c : ((BlockStatement) s).statements) out.addAll(stmts(c))
            return out
        }
        Map node = stmt(s)
        if (node != null) out.add(node)
        return out
    }

    Map stmt(Statement s) {
        if (s instanceof EmptyStatement) return null
        if (s instanceof ExpressionStatement) return exprStmt(((ExpressionStatement) s).expression, s)
        if (s instanceof IfStatement) {
            IfStatement i = (IfStatement) s
            return [k: 'if', cond: text(i.booleanExpression), condCalls: nestedCalls(i.booleanExpression),
                    then: stmts(i.ifBlock), else: stmts(i.elseBlock)] + pos(s)
        }
        if (s instanceof ForStatement) {
            ForStatement f = (ForStatement) s
            return [k: 'for', variable: f.variable?.name, collection: text(f.collectionExpression),
                    collectionCalls: nestedCalls(f.collectionExpression), body: stmts(f.loopBlock)] + pos(s)
        }
        if (s instanceof WhileStatement) {
            WhileStatement w = (WhileStatement) s
            return [k: 'while', cond: text(w.booleanExpression), body: stmts(w.loopBlock)] + pos(s)
        }
        if (s instanceof DoWhileStatement) {
            DoWhileStatement w = (DoWhileStatement) s
            return [k: 'while', cond: text(w.booleanExpression), body: stmts(w.loopBlock)] + pos(s)
        }
        if (s instanceof TryCatchStatement) {
            TryCatchStatement t = (TryCatchStatement) s
            List catches = []
            for (CatchStatement c : t.catchStatements) {
                catches.add([type: c.exceptionType?.name, variable: c.variable?.name, body: stmts(c.code)] + pos(c))
            }
            return [k: 'try', body: stmts(t.tryStatement), catches: catches, finally: stmts(t.finallyStatement)] + pos(s)
        }
        if (s instanceof SwitchStatement) {
            SwitchStatement sw = (SwitchStatement) s
            List cases = []
            for (CaseStatement c : sw.caseStatements) cases.add([value: text(c.expression), body: stmts(c.code)] + pos(c))
            return [k: 'switch', expr: text(sw.expression), cases: cases, default: stmts(sw.defaultStatement)] + pos(s)
        }
        if (s instanceof ReturnStatement) {
            ReturnStatement r = (ReturnStatement) s
            return [k: 'return', value: value(r.expression)] + pos(s)
        }
        if (s instanceof ThrowStatement) return [k: 'throw', text: text(s), calls: nestedCalls(((ThrowStatement) s).expression)] + pos(s)
        if (s instanceof BreakStatement) return [k: 'break'] + pos(s)
        if (s instanceof ContinueStatement) return [k: 'continue'] + pos(s)
        if (s instanceof SynchronizedStatement) {
            return [k: 'synchronized', body: stmts(((SynchronizedStatement) s).code)] + pos(s)
        }
        if (s instanceof AssertStatement) return [k: 'assert', text: text(s)] + pos(s)
        return [k: 'stmt', kind: s.class.simpleName, text: text(s, 400)] + pos(s)
    }

    Map exprStmt(Expression e, Statement s) {
        if (e instanceof MethodCallExpression || e instanceof StaticMethodCallExpression || e instanceof ConstructorCallExpression) {
            return call(e)
        }
        if (e instanceof DeclarationExpression) {
            DeclarationExpression d = (DeclarationExpression) e
            List annotations = []
            for (AnnotationNode a : d.annotations) annotations.add(annotation(a))
            String name = d.isMultipleAssignmentDeclaration() ? text(d.leftExpression) : d.variableExpression?.name
            return [k: 'decl', name: name, value: value(d.rightExpression), annotations: annotations] + pos(e)
        }
        if (e instanceof BinaryExpression && ((BinaryExpression) e).operation.text in ['=', '+=', '-=', '<<']) {
            BinaryExpression b = (BinaryExpression) e
            return [k: 'assign', op: b.operation.text, target: text(b.leftExpression), value: value(b.rightExpression)] + pos(e)
        }
        return [k: 'expr', kind: e.class.simpleName, text: text(e, 400), calls: nestedCalls(e)] + pos(e)
    }

    // ------------------------------------------------------------------- calls
    Map call(Expression e) {
        String name
        String receiver = null
        Expression args
        boolean safe = false
        if (e instanceof MethodCallExpression) {
            MethodCallExpression m = (MethodCallExpression) e
            name = m.methodAsString ?: text(m.method)
            if (!m.isImplicitThis()) receiver = text(m.objectExpression, 300)
            args = m.arguments
            safe = m.safe
        } else if (e instanceof StaticMethodCallExpression) {
            StaticMethodCallExpression m = (StaticMethodCallExpression) e
            name = m.method
            receiver = m.ownerType?.name
            args = m.arguments
        } else {
            ConstructorCallExpression c = (ConstructorCallExpression) e
            name = 'new ' + c.type.name
            args = c.arguments
        }
        List positional = []
        Map named = [:]
        List body = null
        List argExprs = []
        if (args instanceof TupleExpression) argExprs.addAll(((TupleExpression) args).expressions)
        else if (args != null) argExprs.add(args)
        for (int i = 0; i < argExprs.size(); i++) {
            Expression a = argExprs[i]
            if (a instanceof MapExpression) {
                for (MapEntryExpression me : ((MapExpression) a).mapEntryExpressions) {
                    named[keyText(me.keyExpression)] = value(me.valueExpression)
                }
            } else if (a instanceof ClosureExpression && i == argExprs.size() - 1) {
                body = stmts(((ClosureExpression) a).code)
            } else {
                positional.add(value(a))
            }
        }
        Map node = [k: 'call', name: name, args: positional, named: named] + pos(e)
        if (receiver != null) {
            node.receiver = receiver
            // calls chained on the receiver, e.g. docker.image('x').inside { }
            if (e instanceof MethodCallExpression) {
                List rc = nestedCalls(((MethodCallExpression) e).objectExpression)
                if (rc) node.receiverCalls = rc
            }
        }
        if (safe) node.safe = true
        if (body != null) node.body = body
        return node
    }

    String keyText(Expression k) {
        if (k instanceof ConstantExpression) return String.valueOf(((ConstantExpression) k).value)
        return text(k, 200)
    }

    Map annotation(AnnotationNode a) {
        Map members = [:]
        a.members.each { String k, Expression v -> members[k] = value(v) }
        return [name: a.classNode?.nameWithoutPackage ?: a.classNode?.name, members: members] + pos(a)
    }

    // ------------------------------------------------------------------- values
    Map value(Expression e) {
        if (e == null) return null
        if (e instanceof ConstantExpression) {
            Object v = ((ConstantExpression) e).value
            String t = v == null ? 'null' : (v instanceof String ? 'str' : (v instanceof Boolean ? 'bool' : (v instanceof Number ? 'num' : 'const')))
            return [t: t, v: (t == 'const' ? String.valueOf(v) : v)] + pos(e)
        }
        if (e instanceof GStringExpression) {
            GStringExpression g = (GStringExpression) e
            List vars = []
            for (Expression ve : g.values) vars.add(text(ve, 200))
            return [t: 'gstr', v: text(e) ?: g.text, vars: vars, calls: nestedCalls(e)] + pos(e)
        }
        if (e instanceof ListExpression) {
            List items = []
            for (Expression x : ((ListExpression) e).expressions) items.add(value(x))
            return [t: 'list', v: items] + pos(e)
        }
        if (e instanceof MapExpression) {
            Map m = [:]
            for (MapEntryExpression me : ((MapExpression) e).mapEntryExpressions) m[keyText(me.keyExpression)] = value(me.valueExpression)
            return [t: 'map', v: m] + pos(e)
        }
        if (e instanceof ClosureExpression) {
            ClosureExpression c = (ClosureExpression) e
            List params = []
            if (c.parameters) for (Parameter p : c.parameters) params.add(p.name)
            return [t: 'closure', params: params, body: stmts(c.code)] + pos(e)
        }
        if (e instanceof MethodCallExpression || e instanceof StaticMethodCallExpression || e instanceof ConstructorCallExpression) {
            return [t: 'call', call: call(e)] + pos(e)
        }
        if (e instanceof BinaryExpression && ((BinaryExpression) e).operation.text == '+') {
            // string concatenation: Groovy 2.4 positions for these nodes are unreliable, so model it structurally
            BinaryExpression b = (BinaryExpression) e
            return [t: 'concat', parts: [value(b.leftExpression), value(b.rightExpression)]] + pos(e)
        }
        if (e instanceof VariableExpression) return [t: 'var', name: ((VariableExpression) e).name] + pos(e)
        if (e instanceof PropertyExpression) return [t: 'prop', text: text(e, 300), calls: nestedCalls(e)] + pos(e)
        return [t: 'expr', kind: e.class.simpleName, text: text(e, 600), calls: nestedCalls(e)] + pos(e)
    }

    // Collect call nodes nested anywhere in an expression (closures included).
    List nestedCalls(Expression e) {
        List found = []
        if (e == null) return found
        Dumper self = this
        CodeVisitorSupport v = new CodeVisitorSupport() {
            void visitMethodCallExpression(MethodCallExpression call) { found.add(self.call(call)) }
            void visitStaticMethodCallExpression(StaticMethodCallExpression call) { found.add(self.call(call)) }
            void visitConstructorCallExpression(ConstructorCallExpression call) { found.add(self.call(call)) }
            void visitClosureExpression(ClosureExpression c) { found.add([k: 'closure', body: self.stmts(c.code)] + self.pos(c)) }
        }
        e.visit(v)
        return found
    }

    Map method(MethodNode m) {
        List params = []
        for (Parameter p : m.parameters) params.add([name: p.name, type: p.type?.nameWithoutPackage, hasDefault: p.hasInitialExpression()])
        List annotations = []
        for (AnnotationNode a : m.annotations) annotations.add(annotation(a))
        return [name: m.name, params: params, annotations: annotations, body: stmts(m.code)] + pos(m)
    }
}

Map dumpFile(File f) {
    String source = f.getText('UTF-8')
    Map result = [file: f.path, ok: true, errors: [], imports: [], annotations: [], methods: [], classes: [], statements: []]
    CompilerConfiguration cfg = new CompilerConfiguration()
    cfg.setTolerance(0)
    CompilationUnit cu = new CompilationUnit(cfg)
    SourceUnit su = cu.addSource(new SourceUnit(f.name.replaceAll('[^A-Za-z0-9_]', '_'), source, cfg, null, new ErrorCollector(cfg)))
    try {
        cu.compile(Phases.CONVERSION)
    } catch (MultipleCompilationErrorsException ex) {
        result.ok = false
        ex.errorCollector.errors.each { msg ->
            if (msg instanceof SyntaxErrorMessage) {
                SyntaxException se = ((SyntaxErrorMessage) msg).cause
                result.errors.add([message: se.originalMessage, line: se.line, col: se.startColumn])
            } else {
                result.errors.add([message: String.valueOf(msg)])
            }
        }
        return result
    } catch (Throwable t) {
        result.ok = false
        result.errors.add([message: t.toString()])
        return result
    }
    Dumper d = new Dumper(source)
    ModuleNode module = su.AST
    module.imports.each { ImportNode i ->
        List anns = []
        i.annotations.each { anns.add(d.annotation(it)) }
        result.imports.add([name: i.className ?: i.packageName, alias: i.alias, annotations: anns] + d.pos(i))
        result.annotations.addAll(anns)
    }
    (module.starImports + module.staticImports.values() + module.staticStarImports.values()).each { ImportNode i ->
        List anns = []
        i.annotations.each { anns.add(d.annotation(it)) }
        result.imports.add([name: i.className ?: i.packageName, alias: i.alias, annotations: anns] + d.pos(i))
        result.annotations.addAll(anns)
    }
    result.statements = d.stmts(module.statementBlock)
    result.statements.each { s -> if (s.k == 'decl' && s.annotations) result.annotations.addAll(s.annotations) }
    module.methods.each { MethodNode m -> result.methods.add(d.method(m)) }
    module.classes.each { ClassNode c ->
        if (c.isScript()) {
            c.annotations.each { result.annotations.add(d.annotation(it)) }
            return
        }
        List ms = []
        c.methods.each { MethodNode m -> ms.add(d.method(m)) }
        result.classes.add([name: c.nameWithoutPackage, superClass: c.unresolvedSuperClass?.name, methods: ms] + d.pos(c))
    }
    return result
}

List argsList = this.args as List
File outDir = null
int oi = argsList.indexOf('--out')
if (oi >= 0) {
    outDir = new File(argsList[oi + 1])
    argsList = argsList[0..<oi] + (oi + 2 < argsList.size() ? argsList[(oi + 2)..-1] : [])
    outDir.mkdirs()
}
List results = []
argsList.each { String p ->
    File f = new File(p)
    Map r
    try {
        r = dumpFile(f)
    } catch (Throwable t) {
        r = [file: p, ok: false, errors: [[message: 'dumper failure: ' + t.toString()]]]
    }
    if (outDir != null) {
        String name = p.replaceAll('^/+', '').replaceAll('[/\\\\]', '__') + '.ast.json'
        new File(outDir, name).setText(JsonOutput.toJson(r), 'UTF-8')
        System.err.println((r.ok ? 'ok   ' : 'FAIL ') + p)
    } else {
        results.add(r)
    }
}
if (outDir == null) println JsonOutput.toJson(results)

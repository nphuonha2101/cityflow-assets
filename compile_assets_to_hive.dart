// ignore_for_file: avoid_print
import 'dart:convert';
import 'dart:io';
import 'package:hive/hive.dart';

void main(List<String> args) async {
  final String city = args.isNotEmpty ? args[0] : 'hcmc';
  
  // Detect directory structure
  final isFlutterRepo = Directory('assets/data').existsSync();
  final String basePath = isFlutterRepo ? 'assets/data/$city' : '$city';
  final String hiveTempPath = isFlutterRepo ? 'scratch/hive_temp' : 'hive_temp';

  print('=== CityFlow Assets Hive Compiler ===');
  print('Target City: $city');
  print('Base Path: $basePath');

  final tempDir = Directory(hiveTempPath);
  if (tempDir.existsSync()) {
    tempDir.deleteSync(recursive: true);
  }
  tempDir.createSync(recursive: true);
  Hive.init(tempDir.path);

  // 1. Compile Bus Stops
  final stopsJsonFile = File('$basePath/${city}_bus_stops.json');
  if (stopsJsonFile.existsSync()) {
    print('Processing bus stops JSON...');
    final jsonString = stopsJsonFile.readAsStringSync();
    
    // Validate JSON structure
    try {
      jsonDecode(jsonString);
    } catch (e) {
      print('Error: Invalid JSON format in ${stopsJsonFile.path}: $e');
      exit(1);
    }

    final boxName = '${city}_bus_stops';
    final box = await Hive.openBox(boxName);
    await box.put('stops', jsonString);
    await box.close();

    final generatedFile = File('${tempDir.path}/$boxName.hive');
    if (generatedFile.existsSync()) {
      final targetFile = File('$basePath/$boxName.hive');
      generatedFile.copySync(targetFile.path);
      print('Successfully compiled stops to: ${targetFile.path} (${targetFile.lengthSync()} bytes)');
    } else {
      print('Error: Failed to generate Hive box for stops.');
    }
  } else {
    print('Warning: ${stopsJsonFile.path} not found, skipping stops compilation.');
  }

  // 2. Compile Precalculated Routes (if JSON exists)
  final routesJsonFile = File('$basePath/${city}_routes_graph.json');
  if (routesJsonFile.existsSync()) {
    print('Processing precalculated routes JSON...');
    final jsonString = routesJsonFile.readAsStringSync();
    final Map<String, dynamic> rawData = jsonDecode(jsonString);

    final boxName = '${city}_routes_graph';
    final box = await Hive.openBox(boxName);
    await box.putAll(rawData);
    await box.close();

    final generatedFile = File('${tempDir.path}/$boxName.hive');
    if (generatedFile.existsSync()) {
      final targetFile = File('$basePath/$boxName.hive');
      generatedFile.copySync(targetFile.path);
      print('Successfully compiled routes to: ${targetFile.path} (${targetFile.lengthSync()} bytes)');
    } else {
      print('Error: Failed to generate Hive box for routes.');
    }
  } else {
    print('Note: ${routesJsonFile.path} not found, skipping routes compilation.');
  }

  // Clean up
  try {
    tempDir.deleteSync(recursive: true);
  } catch (_) {}
  print('Done!');
}
